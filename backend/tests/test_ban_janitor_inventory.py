"""F1 (fix 1): the janitor's startup inventory still resolves every reachable
statement now that the ban clause is a call to the one definition
(models.player_ban_active_sql).

main._janitor_sql_inventory() is what the boot self-test EXPLAINs; a site it
cannot resolve lands in `dynamic` and the sweep silently stops covering it.
The evaluator resolves a call to the definition ONLY when its one argument
is a positional str literal and the module binds the name by its top-level
`from models import player_ban_active_sql` alone; anything else stays
dynamic. The controls plant each of those shapes, and plant one resolvable
and one unresolvable statement into the live sources to show the exact
numbers move.

The numbers are exact. Main b2ba4b91 reads 350 statements and 0 dynamic, and
so does this lane after F1. On 88a0a2bf (before fix 1) it read 344 and 6:
_pc_take_snapshot, _pc_trade_janitor_step and four tournaments sites
(_player_id_banned, _eligible_entrant_ids, _eligible_slot_tallies,
_queue_availability_notices) were dynamic, the first two through the
evaluator's depth bound and the rest through the call itself.
"""
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import main  # noqa: E402
import models  # noqa: E402

STATEMENTS, DYNAMIC = 350, 0
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
    # each formerly dynamic site is a statement now, carrying the definition's
    # own text for its alias (resolved, not skipped)
    for (module, func), alias in FORMERLY_DYNAMIC.items():
        sqls = [_flat(s["sql"]) for s in inv["statements"] if (s["module"], s["func"]) == (module, func)]
        assert any(models.player_ban_active_sql(alias) in q for q in sqls), (module, func, len(sqls))


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


def _inventory(body):
    src = "from models import player_ban_active_sql\n\n" + textwrap.dedent(body).lstrip("\n")
    inv = main._janitor_sql_from_sources({"main": src}, ROOT)
    return [_flat(s["sql"]) for s in inv["statements"]], [d["line"] for d in inv["dynamic"]]


def test_positive_control_literal_arguments_resolve_to_the_definitions_text():
    sqls, dynamic = _inventory('''
        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
    ''')
    assert dynamic == [] and len(sqls) == 1, (sqls, dynamic)
    assert "SELECT 1 FROM player_bans pb WHERE " + models.player_ban_active_sql("pb") in sqls


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


def test_control_a_keyword_or_a_second_argument_stays_dynamic():
    sqls, dynamic = _inventory('''
        async def root(db):
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql(alias="pb")))
            await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb", "CAST(:t AS timestamptz)")))
    ''')
    assert sqls == [] and dynamic == [4, 5], (sqls, dynamic)


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
    ''')
    assert sqls == [] and dynamic == [4], (sqls, dynamic)
