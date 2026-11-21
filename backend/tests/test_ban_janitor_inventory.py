"""F1 (fix 1): the janitor's startup inventory still resolves every reachable
statement now that the ban clause is a call to the one definition
(models.player_ban_active_sql).

main._janitor_sql_inventory() is what the boot self-test EXPLAINs; a site it
cannot resolve lands in `dynamic` and the sweep silently stops covering it.
The evaluator resolves a call to the definition ONLY when it has one or two
positional str literals and no keyword, through a name a top-level
`from models import player_ban_active_sql` binds that the module census
(the one that decides module constants) admits and the site's function does
not shadow; anything else stays dynamic, and a refused name is listed in
the inventory's `ban_def_refused` with the census's reasons. The controls
plant each of those shapes, every form the census refuses the name for,
and one resolvable and one unresolvable statement into the live sources to
show the exact numbers move.

The numbers are exact. Main b2ba4b91 reads 350 statements and 0 dynamic; this
lane adds ONE janitor statement (the 'ban_ended' read of _pc_snapshot_due),
so the lane's own tip reads 351 and 0. Stacked on the casual-streak stack
(a3fc2562, which reads 360 and 0), the tree reads 361 and 0, as
main._janitor_sql_inventory() measures it. On 88a0a2bf (before fix 1) it read
344 and 6:
_pc_take_snapshot, _pc_trade_janitor_step and four tournaments sites
(_player_id_banned, _eligible_entrant_ids, _eligible_slot_tallies,
_queue_availability_notices) were dynamic, the first two through the
evaluator's depth bound and the rest through the call itself.

Stacked on the mail spam case lock lane (claude/mscl-1116), the tree reads
371 and 0: that lane adds eleven janitor statements (_mail_case_scrub_reporters
1, _mail_case_scrub_resolvers 3, _mail_purge_due 7) and _mail_retention_sweep
goes from 4 to 3, as main._janitor_sql_from_sources measures both trees.

With QDIG-1 merged on that stack, the tree reads 382 and 0: QDIG-1's janitor
pass adds eleven statements (_qdig_janitor_pass 7, _qdig_load 4), every one a
module constant or literal, and no other function's count moves, as
main._janitor_sql_from_sources measures this tree and the stack's.

With QAPPLY-1 (the held-report Accept and Credit), the tree reads 389 and 0:
the report route's body, which the walk reaches from queue_cleanup_loop, now
calls the held-report gate and its record (under the held-report replay
only, which no janitor sets), so seven statements join the inventory
(_qapply_gate 4, _qapply_finish 1, _modlog_write 1, _modlog_steam_ids 1),
every one a module constant or literal and none a session statement, and no
other function's count moves, as main._janitor_sql_from_sources measures
this tree and the base's.

With the game's claim (QAPPLY-1 fix 1), the tree reads 391 and 0: the body
reads the game's claim (_qapply_claim_of 1) and the record takes it
(_qapply_claim 1), both module constants on the claims table, and no other
function's count moves, as main._janitor_sql_from_sources measures this tree
and the review's base.
With the ban sweep (bans part 2a) the tree reads 384 and 0: the janitor
already reaches _check_steam_session and submit_ffa_match, and each now
calls a ban read, so _is_banned (1, through the soft check's ban read) and
_ban_gate_any_or_raise (1, through the FFA report's gate) are counted; both
statements resolve, and no other function's count moves, as
main._janitor_sql_from_sources measures this tree and e3c8b2a2's.

With the ban sweep's fix sitting (FIX-1) the tree reads 385 and 0: the
report window's settle bodies now read the ban themselves under the
identity lock (_settle_writer_ban_check -> _ban_lock_and_gate), and the one
new statement the janitor reaches is that helper's shared identity lock
(1); its ban reads are the gates already counted above.

The fix's second part (FIX-1B) reads 386 and 0: _ban_lock_and_gate takes the
keys its `exclusive=` names in their exclusive form, one more statement the
janitor reaches through the same helper (1); _refund_lobby_bets' open-bet
read gained its bettor filter, a changed statement and not a new one. FIX-2
adds none: the window's close-as-refused statements live in
match_report_window, which this inventory does not read.

With QAPPLY-1 and the ban sweep on one branch (claude/stack-1120) the tree
reads 395 and 0: both lanes counted from the same 382 (QDIG-1), QAPPLY-1
adds nine (382 -> 391) and the ban sweep four (382 -> 386), and no function
is counted by both, so 382 + 9 + 4 = 395, as main._janitor_sql_from_sources
measures the merged tree.
"""
import asyncio
import os
import re
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import main  # noqa: E402
import models  # noqa: E402

STATEMENTS, DYNAMIC = 395, 0   # 391 QAPPLY-1 alone, 386 the ban sweep alone, 382 before both, 371 before QDIG-1 (see the module docstring)
ROOT = (("main", "root"),)
DEF = re.compile(r"\((\w+)\.unbanned_at IS NULL AND \(\1\.expires_at IS NULL OR \1\.expires_at > NOW\(\)\)\)")
# the sites that were dynamic on 88a0a2bf, and the alias each one's definition call names
FORMERLY_DYNAMIC = {
    ("main", "_pc_take_snapshot"): "b",
    ("main", "_pc_trade_janitor_step"): "b",
    ("tournaments", "_player_id_banned"): "pb",
    ("tournaments", "_eligible_entrant_ids"): "pb",
    ("tournaments", "_eligible_slot_tallies"): "pb",
    ("tournaments", "_queue_availability_notices"): "pb",
}


def _flat(sql):
    return " ".join(sql.split())


def test_the_startup_inventory_reads_every_statement_and_none_is_dynamic():
    inv = main._janitor_sql_inventory()
    assert (len(inv["statements"]), len(inv["dynamic"])) == (STATEMENTS, DYNAMIC), (
        len(inv["statements"]), inv["dynamic"])
    assert inv["ban_def_refused"] == [], inv["ban_def_refused"]
    # each formerly dynamic site is a statement now, carrying the definition's
    # own text for its alias (resolved, not skipped)
    for (module, func), alias in FORMERLY_DYNAMIC.items():
        sqls = [_flat(s["sql"]) for s in inv["statements"] if (s["module"], s["func"]) == (module, func)]
        assert any(models.player_ban_active_sql(alias) in q for q in sqls), (module, func, len(sqls))
    # the ban_ended read resolves both forms of the one definition
    due = [_flat(s["sql"]) for s in inv["statements"] if s["func"] == "_pc_snapshot_due"]
    ended = [q for q in due if "AS ban_ended" in q]
    assert len(ended) == 1, due
    assert models.player_ban_active_sql("b", "CAST(:last_at AS timestamptz)") in ended[0]
    assert models.player_ban_active_sql("b") in ended[0] and models.player_ban_active_sql("b2") in ended[0]


def _live_sources():
    """The two sources the startup inventory reads, read the way it reads them."""
    import tournaments
    out = {}
    for name, path in (("main", main.__file__), ("tournaments", tournaments.__file__)):
        with open(path, "r", encoding="utf-8") as fh:
            out[name] = fh.read()
    return out


# a line of _pc_snapshot_due, a function the janitor's roots reach
DUE_ANCHOR = '    if int(due["last_rule"] or 0) < int(_PC_POOL_RULE):\n'


def test_control_a_statement_added_to_a_janitor_function_moves_the_numbers():
    """The exact numbers above are what fails when a statement is added: one
    more statement in a function the janitor reaches reads one more, and one
    the evaluator cannot resolve reads as dynamic. Both are planted into the
    live sources, through the startup's own roots; the unplanted sources read
    the pinned numbers in the same run."""
    src = _live_sources()
    assert src["main"].count(DUE_ANCHOR) == 1
    roots = main._JANITOR_SELFTEST_ROOTS
    base = main._janitor_sql_from_sources(src, roots)
    assert (len(base["statements"]), len(base["dynamic"])) == (STATEMENTS, DYNAMIC)
    added = dict(src, main=src["main"].replace(
        DUE_ANCHOR, '    await db.execute(text("SELECT 417 AS planted"))\n' + DUE_ANCHOR))
    inv = main._janitor_sql_from_sources(added, roots)
    assert (len(inv["statements"]), len(inv["dynamic"])) == (STATEMENTS + 1, DYNAMIC)
    assert [s["func"] for s in inv["statements"] if "SELECT 417 AS planted" in s["sql"]] == ["_pc_snapshot_due"]
    unresolved = dict(src, main=src["main"].replace(
        DUE_ANCHOR, '    await db.execute(text("SELECT " + str(db)))\n' + DUE_ANCHOR))
    inv = main._janitor_sql_from_sources(unresolved, roots)
    assert (len(inv["statements"]), [d["func"] for d in inv["dynamic"]]) == (STATEMENTS, ["_pc_snapshot_due"])


def _src(body):
    return "from models import player_ban_active_sql\n\n" + textwrap.dedent(body).lstrip("\n")


def _inventory(body):
    inv = main._janitor_sql_from_sources({"main": _src(body)}, ROOT)
    return [_flat(s["sql"]) for s in inv["statements"]], [d["line"] for d in inv["dynamic"]]


def _runtime_sql(body):
    """The strings the planted root hands db.execute when it RUNS: the same
    source executed with `text` as the identity, so each one is exactly the
    string the runtime builds."""
    seen = []

    class _DB:
        async def execute(self, q):
            seen.append(q)

    ns = {"text": lambda q: q, "__name__": "planted"}
    exec(compile(_src(body), "planted.py", "exec"), ns)
    asyncio.run(ns["root"](_DB()))
    return seen


def test_positive_control_literal_arguments_resolve_to_the_definitions_text():
    body = '''
        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
            await db.execute(text(f"SELECT 1 FROM player_bans b WHERE {player_ban_active_sql('b', 'CAST(:t AS timestamptz)')}"))
    '''
    sqls, dynamic = _inventory(body)
    assert dynamic == [] and len(sqls) == 2, (sqls, dynamic)
    assert "SELECT 1 FROM player_bans pb WHERE " + models.player_ban_active_sql("pb") in sqls
    assert "SELECT 1 FROM player_bans b WHERE " + models.player_ban_active_sql(
        "b", "CAST(:t AS timestamptz)") in sqls
    # and unnormalised: each inventoried string is the very string the root
    # builds when it runs, character for character, in the order it runs
    inv = main._janitor_sql_from_sources({"main": _src(body)}, ROOT)
    assert [s["sql"] for s in inv["statements"]] == _runtime_sql(body)


def test_control_a_non_literal_alias_stays_dynamic():
    sqls, dynamic = _inventory('''
        async def root(db, a="pb"):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql(a)))
    ''')
    assert sqls == [] and dynamic == [4], (sqls, dynamic)


def test_control_another_function_stays_dynamic():
    sqls, dynamic = _inventory('''
        def other_clause(alias):
            return "(" + alias + ".unbanned_at IS NULL)"

        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + other_clause("pb")))
    ''')
    assert sqls == [] and dynamic == [7], (sqls, dynamic)


def test_control_a_keyword_or_a_third_argument_stays_dynamic():
    sqls, dynamic = _inventory('''
        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql(alias="pb")))
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb", "x", "y")))
    ''')
    assert sqls == [] and dynamic == [4, 5], (sqls, dynamic)


def test_control_a_positional_literal_with_a_keyword_stays_dynamic():
    """One positional literal passes the arity check on its own, so this is
    the call only the keyword refusal keeps dynamic: resolving it while
    ignoring `at` would inventory the current-instant text for a site that
    runs the at-instant one."""
    sqls, dynamic = _inventory('''
        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb", at="CAST(:t AS timestamptz)")))
    ''')
    assert sqls == [] and dynamic == [4], (sqls, dynamic)


def test_control_a_rebound_name_is_not_the_definition():
    sqls, dynamic = _inventory('''
        def player_ban_active_sql(alias):
            return "TRUE"

        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
    ''')
    assert sqls == [] and dynamic == [7], (sqls, dynamic)


def test_control_an_argument_the_definition_refuses_stays_dynamic():
    sqls, dynamic = _inventory('''
        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb;")))
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb", "NOW()")))
    ''')
    assert sqls == [] and dynamic == [4, 5], (sqls, dynamic)


SITE = '''
async def root(db):
    await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
'''


def _planted(plant, site=SITE):
    """The inventory of a module that imports the definition, then runs
    `plant`, then defines the root whose one statement calls the name; and
    the line of that statement."""
    src = ("from models import player_ban_active_sql\n"
           + textwrap.dedent(plant).strip("\n") + "\n\n"
           + textwrap.dedent(site).lstrip("\n"))
    inv = main._janitor_sql_from_sources({"main": src}, ROOT)
    line = 1 + next(i for i, t in enumerate(src.splitlines()) if "await db.execute" in t)
    return inv, line


# Every form the module census refuses the name for (_module_census inside
# main._janitor_sql_from_sources, the census that decides module constants),
# one per branch that blocks or gives the module up, planted after the
# definition's import, with the reason the inventory records. "opaque: ..."
# is a form that may rebind any module name and so refuses every name.
REBINDING_FORMS = [
    # the review's forms
    ("globals-literal-key", 'globals()["player_ban_active_sql"] = lambda a: "FALSE"',
     "namespace store by literal key"),
    ("globals-variable-key", '_k = "player_ban_active_sql"\nglobals()[_k] = lambda a: "FALSE"',
     "opaque: namespace store"),
    ("module-attribute-sys-modules",
     'import sys\nsys.modules[__name__].player_ban_active_sql = lambda a: "FALSE"',
     "namespace attribute store"),
    ("module-attribute-self-import", 'import main\nmain.player_ban_active_sql = lambda a: "FALSE"',
     "attribute store on an imported name"),
    ("setattr-sys-modules",
     'import sys\nsetattr(sys.modules[__name__], "player_ban_active_sql", lambda a: "FALSE")',
     "setattr by a literal name"),
    ("wildcard-import", "from os.path import *", "opaque: import *"),
    # every other namespace form
    ("module-attribute-namespace-alias",
     'import sys\n_m = sys.modules[__name__]\n_m.player_ban_active_sql = lambda a: "FALSE"',
     "namespace attribute store"),
    ("setattr-imported-module", 'import main\nsetattr(main, "player_ban_active_sql", lambda a: "FALSE")',
     "setattr by a literal name"),
    ("setattr-variable-name",
     'import sys\n_k = "player_ban_active_sql"\nsetattr(sys.modules[__name__], _k, lambda a: "FALSE")',
     "opaque: setattr"),
    ("vars-literal-key", 'vars()["player_ban_active_sql"] = lambda a: "FALSE"',
     "namespace store by literal key"),
    ("locals-literal-key", 'locals()["player_ban_active_sql"] = lambda a: "FALSE"',
     "namespace store by literal key"),
    ("module-dict-literal-key",
     'import sys\nsys.modules[__name__].__dict__["player_ban_active_sql"] = lambda a: "FALSE"',
     "namespace store by literal key"),
    ("namespace-method", 'globals().update(player_ban_active_sql=lambda a: "FALSE")',
     "opaque: namespace method"),
    ("namespace-argument", 'dict.update(globals(), player_ban_active_sql=lambda a: "FALSE")',
     "opaque: namespace argument"),
    ("namespace-returned", "def _ns():\n    return globals()", "opaque: namespace escape"),
    ("namespace-yielded", "def _ns():\n    yield globals()", "opaque: namespace escape"),
    ("namespace-yielded-from", "def _ns():\n    yield from globals()", "opaque: namespace escape"),
    ("globals-literal-del", 'del globals()["player_ban_active_sql"]', "namespace store by literal key"),
    ("derived-item-store", '_e = globals()["_cfg"]\n_e["player_ban_active_sql"] = lambda a: "FALSE"',
     "opaque: namespace store"),
    ("derived-attribute-store", '_e = globals()["_cfg"]\n_e.player_ban_active_sql = lambda a: "FALSE"',
     "opaque: namespace store"),
    ("namespace-stored-in-an-object", "import types\n_ns = types.SimpleNamespace()\n_ns.g = globals()",
     "opaque: namespace store"),
    ("setattr-call-target", 'setattr(object(), "player_ban_active_sql", lambda a: "FALSE")',
     "setattr by a literal name"),
    ("namespace-matched", "match globals():\n    case _:\n        pass", "opaque: namespace escape"),
    ("exec", "exec(\"player_ban_active_sql = lambda a: 'FALSE'\")", "opaque: exec"),
    ("eval", 'eval("0")', "opaque: eval"),
    ("dunder-import", '__import__("os")', "opaque: __import__"),
    ("builtins-name", "_b = __builtins__", "opaque: __builtins__"),
    ("builtins-exec", 'import builtins\nbuiltins.exec("0")', "opaque: exec"),
    # every binding of the name itself
    ("module-assignment", 'player_ban_active_sql = lambda a: "FALSE"', "assignment"),
    ("tuple-leaf", 'player_ban_active_sql, _x = (lambda a: "FALSE"), 1', "assignment target"),
    ("chained-assignment", 'player_ban_active_sql = _y = lambda a: "FALSE"', "assignment target"),
    ("starred-leaf", '*player_ban_active_sql, = [lambda a: "FALSE"]', "assignment target"),
    ("augmented", 'player_ban_active_sql += ""', "augmented or annotated assignment"),
    ("annotated", 'player_ban_active_sql: object = lambda a: "FALSE"', "augmented or annotated assignment"),
    ("walrus", '(player_ban_active_sql := lambda a: "FALSE")', "walrus"),
    ("for-target", 'for player_ban_active_sql in (lambda a: "FALSE",):\n    pass', "for target"),
    ("with-alias", "with open(__file__) as player_ban_active_sql:\n    pass", "with alias"),
    ("del", "del player_ban_active_sql", "del"),
    ("comprehension-target", "_xs = [player_ban_active_sql for player_ban_active_sql in ()]",
     "comprehension target"),
    ("def", 'def player_ban_active_sql(alias):\n    return "TRUE"', "def"),
    ("async-def", 'async def player_ban_active_sql(alias):\n    return "TRUE"', "def"),
    ("class", "class player_ban_active_sql:\n    pass", "class"),
    ("except-alias", "try:\n    pass\nexcept Exception as player_ban_active_sql:\n    pass", "except alias"),
    ("match-capture", "match 1:\n    case player_ban_active_sql:\n        pass", "match capture"),
    ("match-mapping-rest", "match {}:\n    case {**player_ban_active_sql}:\n        pass", "match capture"),
    ("match-star", "match []:\n    case [*player_ban_active_sql]:\n        pass", "match capture"),
    ("match-subject", "match player_ban_active_sql:\n    case _:\n        pass", "match"),
    ("global", 'def _g():\n    global player_ban_active_sql\n    player_ban_active_sql = lambda a: "FALSE"',
     "global or nonlocal declaration"),
    ("nonlocal",
     "def _o():\n    player_ban_active_sql = 1\n    def _i():\n"
     "        nonlocal player_ban_active_sql\n        player_ban_active_sql = 2",
     "global or nonlocal declaration"),
    ("second-import", "from models import player_ban_active_sql", "import"),
    ("function-import", "def _f():\n    from models import player_ban_active_sql", "import"),
    ("method-call", "player_ban_active_sql.cache_clear()", "method call"),
    # (a module-level store whose target is not a bare name also blocks every
    # name in that target, the receiver included)
    ("attribute-store", "player_ban_active_sql.x = 1", "assignment target, store through the name"),
    ("subscript-store", "player_ban_active_sql[0] = 1", "assignment target, store through the name"),
    ("attribute-store-in-a-function", "def _s():\n    player_ban_active_sql.x = 1", "store through the name"),
] + ([("type-alias", "type player_ban_active_sql = int", "type alias")]
     if sys.version_info >= (3, 12) else [])


@pytest.mark.parametrize("plant,why", [f[1:] for f in REBINDING_FORMS],
                         ids=[f[0] for f in REBINDING_FORMS])
def test_control_a_form_that_can_rebind_the_name_refuses_the_definition(plant, why):
    inv, line = _planted(plant)
    assert ([s["line"] for s in inv["statements"]], [d["line"] for d in inv["dynamic"]]) == ([], [line]), (
        inv["statements"], inv["dynamic"])
    assert inv["ban_def_refused"] == [
        {"module": "main", "func": None, "name": "player_ban_active_sql", "why": why}], inv["ban_def_refused"]


# A binding inside the site's own function shadows the definition exactly
# where it shadows a module constant (the `bound` set of _analyze_bindings
# inside main._janitor_sql_from_sources, or a class or match in the
# subtree, which refuses expansion there).
FUNCTION_FORMS = [
    ("parameter", '''
        async def root(db, player_ban_active_sql=None):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
     ''', "bound in the function"),
    ("local-assignment", '''
        async def root(db):
            player_ban_active_sql = lambda a: "FALSE"
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
     ''', "bound in the function"),
    ("nested-def", '''
        async def root(db):
            def player_ban_active_sql(a):
                return "FALSE"
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
     ''', "bound in the function"),
    ("class-in-function", '''
        async def root(db):
            class _Row:
                pass
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
     ''', "class or match in the function"),
    ("match-in-function", '''
        async def root(db):
            match db:
                case _:
                    pass
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
     ''', "class or match in the function"),
]


@pytest.mark.parametrize("site,why", [f[1:] for f in FUNCTION_FORMS],
                         ids=[f[0] for f in FUNCTION_FORMS])
def test_control_a_binding_in_the_function_shadows_the_definition(site, why):
    inv, line = _planted("", site)
    assert ([s["line"] for s in inv["statements"]], [d["line"] for d in inv["dynamic"]]) == ([], [line]), (
        inv["statements"], inv["dynamic"])
    assert inv["ban_def_refused"] == [
        {"module": "main", "func": "root", "name": "player_ban_active_sql", "why": why}], inv["ban_def_refused"]


def test_positive_control_an_unrelated_literal_key_globals_store_leaves_the_site_resolved():
    """The shape of main.py's own globals() stores: a literal key naming
    something else blocks that name only."""
    inv, line = _planted('''
        def _tick():
            globals()["_ffa_gather_started_mono"] = None
    ''')
    assert inv["dynamic"] == [] and inv["ban_def_refused"] == [], (inv["dynamic"], inv["ban_def_refused"])
    assert [(s["line"], s["sql"]) for s in inv["statements"]] == [
        (line, "SELECT 1 FROM player_bans pb WHERE " + models.player_ban_active_sql("pb"))]
