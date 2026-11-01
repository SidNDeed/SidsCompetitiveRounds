"""H3: one durable per-player gate across holds and every formation writer.

The source census is DSN-free and names every authorized admission span.  The
live controls exercise open and claim refusals plus the common gate in both
target orders for all four queue modes.  CF_TEST_PG_DSN/CF_TEST_PG_OPTOUT have
the same meaning as in the other match-hold PostgreSQL suites.
"""

import asyncio
import ast
import collections
import inspect
import os
import re
import sys
import textwrap
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import cf_pg  # noqa: E402
import main  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402
# The match_hold the hold suite loaded: the MATCH_HOLD_SRC copy when set
# (a plain import here would bind the tracked copy main cached).
match_hold = hold_test.match_hold


ACQUIRERS = ("_lease_acquire", "_lease_acquire_many")
GATE = "_lease_admission_gate"
Site = collections.namedtuple("Site", "lineno end_lineno callee held")
_INVENTORY = {}


def admission_sites():
    """Every admission call in main.py by the module-level function that makes
    it, in source order: a call of _lease_acquire, _lease_acquire_many or the
    gate itself.  `held` marks an acquire made with _gate_held=True, the form
    a direct gate caller uses after its own gate.  Derived from the AST, not
    listed by hand: a site a reviewer forgot is a site this inventory shows
    and the census below refuses (the re-land's Codex round, F2, found four
    hand-listed omissions: queue_ready's two sites and both continuations)."""
    if "sites" not in _INVENTORY:
        tree = ast.parse(inspect.getsource(main))
        sites = {}
        for fn in tree.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            found = []
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ACQUIRERS + (GATE,)):
                    held = any(kw.arg == "_gate_held" and isinstance(kw.value, ast.Constant)
                               and kw.value.value is True for kw in node.keywords)
                    found.append(Site(node.lineno, node.end_lineno, node.func.id, held))
            if found:
                sites[fn.name] = sorted(found)
        _INVENTORY["sites"], _INVENTORY["tree"] = sites, tree
    return _INVENTORY["sites"]


def formation_sites():
    """(function, k) of every formation site: an unheld acquirer call outside
    the acquirers, k its source-order index among the function's calls."""
    return sorted((name, k) for name, sites in admission_sites().items()
                  if name not in ACQUIRERS
                  for k, site in enumerate(sites, 1)
                  if site.callee in ACQUIRERS and not site.held)


# The census: every function of main.py that makes an admission call, with
# its calls in source order. The two acquirers gate once, and _lease_acquire_many
# then acquires per player under the gate it holds; _rdm_claim gates directly
# and acquires under that gate. Every other entry is a formation site, whose
# refusal takes the shared form checked below. queue_poll, queue_ready and
# team_queue_poll carry two sites each: the polls' room issuance (first in
# source) and their discovery or assembly, in different requests; queue_ready's
# formation renewal and its in-game fence, in one request.
CENSUS = {
    "_lease_acquire": [(GATE, False)],
    "_lease_acquire_many": [(GATE, False), ("_lease_acquire", True)],
    "queue_poll": [("_lease_acquire_many", False)] * 2,
    "queue_ready": [("_lease_acquire_many", False)] * 2,
    "team_queue_poll": [("_lease_acquire_many", False)] * 2,
    "_team_relock_existing_series": [("_lease_acquire_many", False)],
    "team_series_continuation": [("_lease_acquire_many", False)],
    "ovt_queue_poll": [("_lease_acquire_many", False)],
    "ovt_series_continuation": [("_lease_acquire_many", False)],
    "_lobby_enroll_caller": [("_lease_acquire", False)],
    "team_lobby_start": [("_lease_acquire_many", False)],
    "ovt_lobby_start": [("_lease_acquire_many", False)],
    "_ffa_lobby_enroll_caller": [("_lease_acquire", False)],
    "_ffa_lock_roster": [("_lease_acquire_many", False)],
    "_rdm_claim": [(GATE, False), ("_lease_acquire", True)],
    "_ffa_queue_poll_inner": [("_lease_acquire_many", False)],
}


def _statement_of(fn, node):
    """The statement of `fn` that holds `node`."""
    parents = {c: p for p in ast.walk(fn) for c in ast.iter_child_nodes(p)}
    while not isinstance(node, ast.stmt):
        node = parents[node]
    return node


def _next_statement(fn, stmt):
    """The statement right after `stmt` in the statement list that holds it,
    or None."""
    for parent in ast.walk(fn):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(parent, field, None)
            if isinstance(block, list):
                for i, st in enumerate(block):
                    if st is stmt:
                        return block[i + 1] if i + 1 < len(block) else None
    return None


def _is_db_rollback(stmt):
    """Whether `stmt` is the statement `await db.rollback()`."""
    call = (stmt.value.value if isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Await) else None)
    return (isinstance(call, ast.Call) and not call.args and not call.keywords
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "rollback"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "db")


def _awaits_or_ends(node):
    return any(isinstance(n, ast.Await)
               or (isinstance(n, ast.Attribute) and n.attr in ("commit", "rollback"))
               for n in ast.walk(node))


def refusal_branch_violation(fn, call, form):
    """None when the admission call `call` in function `fn` is answered by its
    own refusal branch in the shape `form` requires, else why not. The branch
    itself is read, never the text after the call: a later rollback in the
    same function answers nothing for this call (rehearsal-four round 1,
    finding 7, where a refusal that commits passed because the loop's
    exhausted-attempts rollback sat in the same tail).

      shared    the formation sites: `if (await <acquirer>(...)) is False:`,
                whose first statement is `await db.rollback()` and whose last
                is a raise, with nothing between that awaits or ends a
                transaction -- the loser rolls back its whole transaction
                (H3) before it answers;
      direct    _rdm_claim: `admitted, _ = await _lease_admission_gate(...)`
                followed at once by `if not admitted:`, whose first statement
                is `return await _rdm_refuse(..., "other_mode")`, before any
                write;
      acquirer  the two acquirers: the same gate form, refused at once by
                `return False` (the caller rolls back);
      hold      match_hold open and claim: the same gate form, refused at
                once by `await db.rollback()`."""
    stmt = _statement_of(fn, call)
    if form == "shared":
        test = getattr(stmt, "test", None)
        if not (isinstance(stmt, ast.If) and isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Await) and test.left.value is call
                and len(test.ops) == 1 and isinstance(test.ops[0], ast.Is)
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value is False):
            return "the acquisition is not tested `is False` by its own if"
        body = stmt.body
        if not _is_db_rollback(body[0]):
            return "the refusal branch does not open with await db.rollback()"
        if len(body) < 2 or not isinstance(body[-1], ast.Raise):
            return "the refusal branch does not end in a raise"
        if any(_awaits_or_ends(st) for st in body[1:]):
            return ("the refusal branch awaits or ends a transaction after "
                    "its rollback")
        return None
    target = stmt.targets[0] if isinstance(stmt, ast.Assign) else None
    value = getattr(stmt, "value", None)
    if not (isinstance(value, ast.Await) and value.value is call
            and isinstance(target, ast.Tuple) and target.elts
            and isinstance(target.elts[0], ast.Name)):
        return "the gate's answer is not unpacked into a name"
    flag = target.elts[0].id
    branch = _next_statement(fn, stmt)
    test = getattr(branch, "test", None)
    if not (isinstance(branch, ast.If) and isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name) and test.operand.id == flag):
        return f"the gate's answer is not refused at once by `if not {flag}:`"
    first = branch.body[0]
    if form == "hold":
        if not _is_db_rollback(first):
            return "the refusal branch does not open with await db.rollback()"
        return None
    if form == "acquirer":
        if not (isinstance(first, ast.Return)
                and isinstance(first.value, ast.Constant)
                and first.value.value is False):
            return "the refusal branch does not open with return False"
        return None
    value = getattr(first, "value", None)
    refused = getattr(value, "value", None)
    if not (isinstance(first, ast.Return) and isinstance(value, ast.Await)
            and isinstance(refused, ast.Call)
            and isinstance(refused.func, ast.Name)
            and refused.func.id == "_rdm_refuse" and refused.args
            and isinstance(refused.args[-1], ast.Constant)
            and refused.args[-1].value == "other_mode"):
        return ('the refusal branch does not open with '
                'return await _rdm_refuse(..., "other_mode")')
    return None


def test_h3_every_admission_site_uses_shared_gate_recheck_and_rollback():
    gate = inspect.getsource(main._lease_admission_gate)
    assert "for pid in pid_text:" in gate
    assert "FOR NO KEY UPDATE" in gate
    assert "queue_leases" in gate and "match_seat_holds" in gate
    assert "ranked_queue" in gate and "team_queue" in gate
    assert "ovt_queue" in gate and "ffa_queue" in gate
    assert "clock_timestamp()" in gate

    found = admission_sites()
    assert {name: [(s.callee, s.held) for s in sites] for name, sites in found.items()} \
        == CENSUS, ("H3 census", found)
    functions = {fn.name: fn for fn in _INVENTORY["tree"].body
                 if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name, sites in found.items():
        for k, site in enumerate(sites):
            if site.held:
                # An acquire under a gate the function holds: the gate is an
                # earlier call of the same function.
                assert any(s.callee == GATE for s in sites[:k]), (name, site)
                continue
            # Every other call is answered by its own refusal branch, read in
            # that branch (rehearsal-four round 1, finding 7).
            call = next(node for node in ast.walk(functions[name])
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == site.callee
                        and node.lineno == site.lineno)
            form = ("shared" if site.callee != GATE
                    else "acquirer" if name in ACQUIRERS else "direct")
            why = refusal_branch_violation(functions[name], call, form)
            assert why is None, (name, site, form, why)

    open_source = inspect.getsource(match_hold.match_hold_open)
    claim_source = inspect.getsource(match_hold.match_hold_claim)
    for name, source in (("open", open_source), ("claim", claim_source)):
        fn = ast.parse(textwrap.dedent(source)).body[0]
        calls = [node for node in ast.walk(fn)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "_lease_admission_gate"]
        assert [c.func.id for c in calls] == ["_lease_admission_gate"], (name, calls)
        # The loser rolls back its whole transaction first (H3), in the
        # branch that refuses, not somewhere in the function.
        why = refusal_branch_violation(fn, calls[0], "hold")
        assert why is None, (name, why)
    assert "admitted, now = await _lease_admission_gate" in open_source
    assert "admitted, now = await _lease_admission_gate" in claim_source
    assert "_gate_held=True" in claim_source
    for helper in (main._lease_acquire, main._lease_acquire_many):
        source = inspect.getsource(helper)
        calls = [node.func.id for node in ast.walk(
            ast.parse(textwrap.dedent(source)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_lease_admission_gate"]
        assert calls == ["_lease_admission_gate"], helper.__name__


def test_h3_refusal_branch_oracle_can_fail():
    """Negative control (#391) for refusal_branch_violation: one planted
    refusal per way a branch can fail its form, beside the shapes that keep
    it, each refused for its own reason."""
    NL = chr(10)

    def why(lines, callee, form):
        fn = ast.parse(NL.join(["async def site(db, ctx, pid, me, n):"]
                               + ["    " + ln for ln in lines])).body[0]
        call = next(node for node in ast.walk(fn)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == callee)
        return refusal_branch_violation(fn, call, form)

    acquire = "if (await _lease_acquire_many(db, ids, 'ranked', None, 1)) is False:"
    refuse = '    raise HTTPException(status_code=503, detail="admission_contended")'
    later = ["for _ in range(3):", "    pass", "else:", "    await db.rollback()"]
    gate = "admitted, _ = await _lease_admission_gate(db, [pid], 'ffa', None)"
    rdm = '    return await _rdm_refuse(ctx, pid, me, "claim", n, "other_mode")'

    assert why([acquire, "    await db.rollback()", refuse] + later,
               "_lease_acquire_many", "shared") is None
    assert why([gate, "if not admitted:", rdm], GATE, "direct") is None
    assert why([gate, "if not admitted:", "    return False"],
               GATE, "acquirer") is None
    assert why(["admitted, now = await _lease_admission_gate(db, [pid], 'ffa', None)",
                "if not admitted:", "    await db.rollback()",
                "    await _install_database_timeouts(db)"], GATE, "hold") is None

    planted = [
        # finding 7 (M1a): the refusal commits; a later rollback answers
        # nothing for it
        ("does not open with await db.rollback()", "_lease_acquire_many",
         "shared", [acquire, "    await db.commit()", refuse] + later),
        ("does not open with await db.rollback()", "_lease_acquire_many",
         "shared", [acquire, refuse] + later),
        ("does not open with await db.rollback()", "_lease_acquire_many",
         "shared", [acquire, "    await note(db)", "    await db.rollback()",
                    refuse]),
        ("awaits or ends a transaction after its rollback",
         "_lease_acquire_many", "shared",
         [acquire, "    await db.rollback()", "    await db.execute(w)", refuse]),
        ("does not end in a raise", "_lease_acquire_many", "shared",
         [acquire, "    await db.rollback()"]),
        ("not tested `is False` by its own if", "_lease_acquire_many",
         "shared", [acquire.replace("is False", "is not False"),
                    "    await db.rollback()", refuse]),
        ("not tested `is False` by its own if", "_lease_acquire_many",
         "shared", ["ok = await _lease_acquire_many(db, ids, 'ranked', None, 1)",
                    "if ok is False:", "    await db.rollback()", refuse]),
        ("does not open with return await _rdm_refuse", GATE, "direct",
         [gate, "if not admitted:", "    pass", rdm.strip()]),
        ("does not open with return await _rdm_refuse", GATE, "direct",
         [gate, "if not admitted:", rdm.replace("other_mode", "other_lobby")]),
        ("is not refused at once by `if not admitted:`", GATE, "direct",
         [gate, "x = 1", "if not admitted:", rdm]),
        ("not unpacked into a name", GATE, "direct",
         ["await _lease_admission_gate(db, [pid], 'ffa', None)",
          "if not admitted:", rdm]),
        ("does not open with return False", GATE, "acquirer",
         [gate, "if not admitted:", "    pass", "return False"]),
        ("does not open with await db.rollback()", GATE, "hold",
         [gate, "if not admitted:", "    await _install_database_timeouts(db)",
          "    await db.rollback()"]),
    ]
    for expected, callee, form, lines in planted:
        got = why(lines, callee, form)
        assert got is not None and expected in got, (expected, form, got)


def test_h3_hold_open_and_claim_reject_another_live_commitment(monkeypatch):
    async def body(env):
        series, game, _ = await hold_test.opened_series(env, "team", held=1)
        held_pid = series.pid(1)
        other_group = uuid.uuid4()
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at) "
            "VALUES ($1, 'ffa', $2, gen_random_uuid(), clock_timestamp() + interval '5 min')",
            held_pid, other_group)

        refused = await hold_test.open_hold(env, series, 1, 0, game)
        assert refused.status_code == 200 and refused.json() == {
            "status": "refused", "reason": "other_mode"}
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE player_id=$1", held_pid) == 0
        assert await env.conn.fetchval(
            "SELECT group_id FROM queue_leases WHERE player_id=$1", held_pid) == other_group

        await env.conn.execute("DELETE FROM queue_leases WHERE player_id=$1", held_pid)
        opened = await hold_test.open_hold(env, series, 1, 0, game)
        assert opened.status_code == 200 and opened.json()["status"] == "opened"
        hold_id = uuid.UUID(opened.json()["hold_id"])
        same_mode_other_group = uuid.uuid4()
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at) "
            "VALUES ($1, 'team', $2, gen_random_uuid(), clock_timestamp() + interval '5 min')",
            held_pid, same_mode_other_group)
        claimed = await hold_test.claim(env, series, 1, hold_id)
        assert claimed == {"status": "refused", "reason": "other_mode"}
        row = await env.conn.fetchrow(
            "SELECT claimed_at, verifier FROM match_seat_holds WHERE id=$1", hold_id)
        assert tuple(row) == (None, None)
        assert await env.conn.fetchval(
            "SELECT group_id FROM queue_leases WHERE player_id=$1", held_pid) == same_mode_other_group

    hold_test.run_env(monkeypatch, body, "h3hold")


@pytest.mark.parametrize("mode", ["ranked", "team", "ovt", "ffa"])
@pytest.mark.parametrize("first", [0, 1])
def test_h3_common_gate_serializes_every_mode_in_both_target_orders(mode, first):
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case("h3gate") as (case, sm):
            seats = await hold_test.seed_players(case.conn, 2)
            pids = [row[0] for row in seats]
            groups = [None, None] if mode == "ranked" else [uuid.uuid4(), uuid.uuid4()]
            winner = groups[first]
            loser = groups[1 - first]
            async with sm() as one, sm() as two:
                admitted, _ = await main._lease_admission_gate(one, pids, mode, winner)
                assert admitted
                for pid in sorted(pids, key=str):
                    await main._lease_acquire(
                        one, pid, mode, winner, main.LEASE_TTL_ASSEMBLY,
                        _gate_held=True)

                waiting = asyncio.create_task(
                    main._lease_admission_gate(two, pids, mode, loser))
                await asyncio.sleep(0.05)
                assert not waiting.done(), "overlapping roster did not wait on the player gate"
                await one.commit()
                admitted_two, _ = await asyncio.wait_for(waiting, 2)
                assert not admitted_two
                await two.rollback()

            rows = await case.conn.fetch(
                "SELECT player_id, mode, group_id FROM queue_leases ORDER BY player_id::text")
            assert len(rows) == 2
            assert all(row["mode"] == mode and row["group_id"] == winner for row in rows)

    asyncio.run(inside())
