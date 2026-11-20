"""Bans part 2a (BAN-R10): an actively banned admin holds no admin power, and
_is_admin (with _require_admin on it) refuses one "Not an admin". The one
admin route that told a banned admin "banned" before this lane,
admin_mail_broadcast (its sender gates read the sender's ban after the
idempotency replay), keeps that answer through _require_admin_roster, the
roster check without the ban read. This file holds that exception to its
one route and its gate to its place; the answers themselves are tested in
test_mail.py (test_broadcast_obeys_the_sender_gates,
test_broadcast_replay_precedes_the_mutable_sender_gates).

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


def _callers(src, name):
    tree = ast.parse(src)
    out = set()
    for fn in tree.body:
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name:
                    out.add(fn.name)
    return out


def _gate_failures(src_of):
    """For each roster-only caller: the roster check comes before the replay,
    the replay before the sender gates, the sender gates before any write."""
    out = []
    for name, src in src_of.items():
        order = [src.find(w) for w in ("_require_admin_roster(", "_mail_prior_send(",
                                       "_mail_sender_gates(", "INSERT INTO")]
        if -1 in order or order != sorted(order):
            out.append((name, order))
    return out


def test_only_the_broadcast_takes_the_roster_check_alone():
    with open(MAIN_PY, encoding="utf-8") as fh:
        src = fh.read()
    assert _callers(src, "_require_admin_roster") == ROSTER_ONLY
    assert _callers(src, "_is_admin_roster") == {"_is_admin", "_require_admin_roster"}
    srcs = {n: textwrap.dedent(inspect.getsource(getattr(main, n))) for n in ROSTER_ONLY}
    assert _gate_failures(srcs) == []


def test_planted_roster_caller_without_the_sender_gates_is_refused():
    planted = ("async def admin_planted(req, db):\n"
               "    await _require_admin_roster(db, req.a, 'x', 'y', req.s)\n"
               "    await db.execute(text('INSERT INTO mail_messages VALUES (1)'))\n")
    assert _callers(planted, "_require_admin_roster") == {"admin_planted"}
    assert [n for n, _ in _gate_failures({"admin_planted": planted})] == ["admin_planted"]
