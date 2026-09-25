"""The janitor SQL self-test walker (main._janitor_sql_from_sources), run
statically. The live inventory must have no `dynamic` site — each one is a
synthetic self-test FAILURE at boot — the Player Cards janitor steps must be
in the reachable set, and module-level constants resolve under exactly the
rules the walker documents (Sept 10 batch, walker r10)."""
import ast
import os
import sys
import textwrap

import pytest

import main

ROOT = (("main", "root"),)


def _sqls(src):
    inv = main._janitor_sql_from_sources({"main": textwrap.dedent(src).lstrip("\n")}, ROOT)
    return (sorted(" ".join(s["sql"].split()) for s in inv["statements"]),
            [d["line"] for d in inv["dynamic"]])


def test_the_live_inventory_resolves_every_reachable_site():
    inv = main._janitor_sql_inventory()
    assert inv["dynamic"] == [], inv["dynamic"]
    funcs = {s["func"] for s in inv["statements"]}
    assert {"_pc_snapshot_janitor_step", "_pc_take_snapshot", "_pc_reconcile_earned_packs",
            "_pc_grant_earned_packs", "_podium_player_ids", "_publish_pair_sitting",
            "_pc_edition_rollover"} <= funcs
    sqls = [" ".join(s["sql"].split()) for s in inv["statements"]]
    assert sum("rs.winner_id AS w1" in q for q in sqls) == 1
    assert sum("UPDATE pc_packs p SET status = 'voided'" in q for q in sqls) == 4
    assert sum("INSERT INTO pc_packs (player_id, source, mode, kind, reference_id, status)" in q for q in sqls) == 1
    assert any("pg_advisory_xact_lock(hashtext('dcpair:'" in q for q in sqls)
    # the podium statements bind the active window; no query interpolates the env int
    assert any("make_interval(days => CAST(:active_days AS integer))" in q for q in sqls)
    assert not any("make_interval(days => 90)" in q for q in sqls)
    # The edition rollover is ONE statement on purpose: the close, the
    # successor insert and the Discord notice commit together or not at all.
    # Asserted AS one statement. Counting "some query holds the INSERT" and
    # "some query holds the UPDATE" separately is satisfied by TWO queries,
    # which is exactly the atomicity the sentence above forbids losing.
    _norm = [" ".join(q.split()) for q in sqls]
    rollover = [q for q in _norm
                if "INSERT INTO pc_editions (id, name, started_at, ends_at_planned)" in q]
    assert len(rollover) == 1, (
        "expected exactly one rollover statement, found %d" % len(rollover))
    assert "UPDATE pc_editions e SET ended_at = now()" in rollover[0], (
        "the close is not in the same statement as the successor insert")
    assert "pending_channel_posts" in rollover[0], (
        "the edition notice is not in the same statement as the rollover")


def test_a_module_string_constant_resolves_at_a_text_site():
    sqls, dyn = _sqls('''
        Q = "SELECT 1"
        async def root(db):
            await db.execute(text(Q))
    ''')
    assert sqls == ["SELECT 1"] and dyn == []


def test_an_fstring_over_module_constants_expands_and_a_later_definition_still_counts():
    sqls, dyn = _sqls('''
        async def root(db):
            await db.execute(text(Q))
        T = "players"
        Q = f"SELECT 1 FROM {T} WHERE x = " + "2"
    ''')
    assert sqls == ["SELECT 1 FROM players WHERE x = 2"] and dyn == []


def test_a_module_dict_constant_drives_a_loop_through_items():
    sqls, dyn = _sqls('''
        D = {"a": "SELECT 1", "b": "SELECT 2"}
        def peek():
            return D.get("a"), list(D.keys())
        async def root(db):
            for k, sql in D.items():
                await db.execute(text(sql))
    ''')
    assert sqls == ["SELECT 1", "SELECT 2"] and dyn == []


def test_a_local_binding_or_parameter_shadows_the_module_constant():
    sqls, dyn = _sqls('''
        Q = "SELECT 1"
        async def root(db):
            Q = "SELECT 2"
            await db.execute(text(Q))
    ''')
    assert sqls == ["SELECT 2"] and dyn == []
    sqls, dyn = _sqls('''
        Q = "SELECT 1"
        async def root(db, Q="SELECT 3"):
            await db.execute(text(Q))
    ''')
    assert sqls == [] and len(dyn) == 1


def test_a_module_constant_resolves_to_its_import_time_value_never_the_site_loops():
    # c3 D1 / c5 E: a module constant that reads a name a SITE loop rebinds
    # keeps its import-time value — resolved against the MODULE's names, not
    # the site's shadowed view of them
    sqls, dyn = _sqls('''
    T = "missing"
    Q = f"SELECT * FROM {T}"
    async def root(db):
        for T in ("players",):
            await db.execute(text(Q))
    ''')
    assert sqls == ["SELECT * FROM missing"] and dyn == [], (sqls, dyn)
    # a binding inside ANOTHER function (a parameter, a loop target) binds
    # that scope's name, never the module's (c5 E)
    sqls, dyn = _sqls('''
    T = "players"
    Q = f"SELECT * FROM {T}"
    def other(T):
        for T in ("x",):
            pass
    async def root(db):
        await db.execute(text(Q))
    ''')
    assert sqls == ["SELECT * FROM players"] and dyn == [], (sqls, dyn)


@pytest.mark.parametrize("src", [
    # declared global (and stored) in another function
    '''
    Q = "SELECT 1"
    def flip():
        global Q
        Q = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    # a second module-level binding, even a conditional one
    '''
    Q = "SELECT 1"
    if True:
        Q = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    # augmented, imported or loop-bound anywhere
    '''
    Q = "SELECT 1"
    Q += " "
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    from x import Q
    Q = "SELECT 1"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    for Q in ("a",):
        pass
    async def root(db):
        await db.execute(text(Q))
    ''',
    # an env-derived part is not a value the walker may invent
    '''
    N = int(os.environ.get("N", "1"))
    Q = f"SELECT {N}"
    async def root(db):
        await db.execute(text(Q))
    ''',
    # a mutable constant that escapes, or is mutated, may not be what the loop reads
    '''
    D = {"a": "SELECT 1"}
    def helper(x):
        x["a"] = "SELECT 9"
    async def root(db):
        helper(D)
        for k, sql in D.items():
            await db.execute(text(sql))
    ''',
    '''
    D = {"a": "SELECT 1"}
    D.update({"a": "SELECT 9"})
    async def root(db):
        for k, sql in D.items():
            await db.execute(text(sql))
    ''',
    # c3 D3: a star import may rebind anything
    '''
    Q = "SELECT 1"
    from x import *
    async def root(db):
        await db.execute(text(Q))
    ''',
    # c3 D4: indirect namespace stores — a constant key, a variable key, a
    # method on the namespace dict, setattr on the module object, exec
    '''
    Q = "SELECT 1"
    def flip():
        globals()["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip(k):
        globals()[k] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip():
        globals().update(Q="SELECT 9")
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    import sys
    Q = "SELECT 1"
    def flip():
        setattr(sys.modules[__name__], "Q", "SELECT 9")
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip():
        exec("Q = 'SELECT 9'")
    async def root(db):
        await db.execute(text(Q))
    ''',
    # c5 E: a name bound to the namespace (transitively) is the namespace;
    # a namespace handed to a callee may be written by it
    '''
    Q = "SELECT 1"
    def flip():
        ns = globals()
        ns["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    import sys
    Q = "SELECT 1"
    def flip():
        m = sys.modules[__name__]
        m.Q = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    import sys
    Q = "SELECT 1"
    def flip():
        sys.modules[__name__].__dict__["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip():
        other(globals())
    async def root(db):
        await db.execute(text(Q))
    ''',
    # c6 E: the namespace VALUE under other spellings, aliases made by other
    # binding forms, escapes the census cannot follow, an indirect exec
    '''
    Q = "SELECT 1"
    def flip():
        flip.__globals__["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    import sys
    Q = "SELECT 1"
    def flip():
        sys.modules.get(__name__).Q = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    import sys
    Q = "SELECT 1"
    def flip():
        sys._getframe().f_globals["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    import sys
    Q = "SELECT 1"
    def flip():
        vars(sys.modules[__name__])["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip(ns=globals()):
        ns["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip():
        for ns in (globals(),):
            ns["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip():
        a, ns = 1, globals()
        ns["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def flip():
        other(*(globals(),))
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    def ns():
        return globals()
    def flip():
        ns()["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    ns = lambda: globals()
    def flip():
        ns()["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    class Box:
        pass
    def flip():
        b = Box()
        b.ns = globals()
        b.ns["Q"] = "SELECT 9"
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    import builtins
    Q = "SELECT 1"
    def flip():
        builtins.exec("Q = 'SELECT 9'")
    async def root(db):
        await db.execute(text(Q))
    ''',
    '''
    Q = "SELECT 1"
    run = exec
    def flip():
        run("Q = 'SELECT 9'")
    async def root(db):
        await db.execute(text(Q))
    ''',
])
def test_a_module_name_that_could_change_stays_dynamic(src):
    sqls, dyn = _sqls(src)
    assert sqls == [] and len(dyn) == 1, (sqls, dyn)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match statements")
def test_a_module_level_match_capture_rebinds_by_name_string():
    # c3 D2: MatchAs / MatchStar / MatchMapping bind names as STRINGS, not Name stores
    for pattern in ("case [Q]:", "case [*Q]:", "case {**Q}:"):
        sqls, dyn = _sqls(f'''
        import sys
        Q = "SELECT 1"
        match sys.argv:
            {pattern}
                pass
        async def root(db):
            await db.execute(text(Q))
        ''')
        assert sqls == [] and len(dyn) == 1, (pattern, sqls, dyn)


def test_a_constant_key_namespace_store_of_another_name_leaves_the_constant_resolvable():
    # negative control (#391): main.py stores globals()["_ffa_gather_*"]; the
    # live inventory must stay green
    sqls, dyn = _sqls('''
    Q = "SELECT 1"
    def flip():
        globals()["OTHER"] = 1
        setattr(obj, "Q", 2)
    async def root(db):
        await db.execute(text(Q))
    ''')
    assert sqls == ["SELECT 1"] and dyn == [], (sqls, dyn)
    # ... and the ordinary idioms around it stay ordinary (c6 E): a method
    # on a plain object, vars() of a plain object, a plain dict store
    sqls, dyn = _sqls('''
    Q = "SELECT 1"
    class Box:
        def snapshot(self):
            return dict(vars(self))
    def flip(obj, d):
        obj.update(x=1)
        d["Q"] = 2
    async def root(db):
        await db.execute(text(Q))
    ''')
    assert sqls == ["SELECT 1"] and dyn == [], (sqls, dyn)
def test_the_shipped_rollover_sql_pins_both_arms_to_utc():
    """Both month-steps in the rollover must be UTC-pinned, in the SHIPPED constant.

    PostgreSQL adds a month interval in the session TimeZone, so
    `ends_at_planned + make_interval(months => 4)` lands on a wall clock, not
    an instant, and crosses a DST boundary an hour (and sometimes a day) away
    from where it should. The fix wraps each step as
    `((x AT TIME ZONE 'UTC') + make_interval(...)) AT TIME ZONE 'UTC'`.

    The expression appears TWICE -- once projected by the SELECT arm and once
    in the WHERE arm that chooses the row -- so there are FOUR conversions in
    total. Pinning one arm and not the other is the dangerous partial fix:
    the predicate would choose one candidate while the projection returned a
    different instant, and no test that only compares two values would say so.

    This lives here, NOT in test_pc_edition_rollover.py, on purpose: that
    module is skipped whole unless PC_EDITION_TEST_PG_DSN is set, so on every
    machine without a live PostgreSQL -- which is most of them, including the
    seat this was written on -- nothing checked this at all. The live-DSN
    tests prove the arithmetic; this one proves the shipped text still has
    the shape those tests assume, and it runs everywhere.
    """
    sql = " ".join(main._PC_EDITION_ROLLOVER_SQL.split())
    pinned = ("((closed.prev_planned AT TIME ZONE 'UTC') "
              "+ make_interval(months => 4 * n)) AT TIME ZONE 'UTC'")
    assert sql.count(pinned) == 2, (
        "expected the UTC-pinned month step in BOTH the SELECT and WHERE arms "
        "(2 occurrences, 4 conversions); found %d" % sql.count(pinned))
    assert sql.count("AT TIME ZONE 'UTC'") == 4, (
        "expected exactly 4 UTC conversions, found %d" % sql.count("AT TIME ZONE 'UTC'"))
    for naive in ("cur.ends_at_planned + make_interval",
                  "closed.prev_planned + make_interval"):
        assert naive not in sql, (
            "an unpinned month step survives in the shipped rollover SQL: %s" % naive)

    # The successor anchor must come from the row the statement actually
    # closed, re-read under its own lock -- never from the cur CTE, which is
    # this statement's snapshot and can be stale by the time the UPDATE wins
    # a contended lock. See the comments on the closed/ins CTEs.
    assert "RETURNING e.id AS prev_id, e.ends_at_planned AS prev_planned" in sql, (
        "closed no longer returns the live planned end")
    assert "cur.ends_at_planned AT TIME ZONE" not in sql, (
        "the successor anchor reads the stale cur snapshot again")
    for live in ("AND e.ends_at_planned IS NOT NULL", "AND e.ends_at_planned <= now()"):
        assert live in sql, (
            "the close no longer re-validates the live schedule: %s" % live)
def test_the_live_postgres_rollover_module_cannot_silently_collect_nothing():
    """Guard the DSN-gated sibling from the outside, where it always runs.

    test_pc_edition_rollover.py used to be SKIPPED whole unless its DSN
    variable was set, so on most machines it contributed nothing -- and a
    NEAR-MISS variable name produced "10 skipped, exit 0", which reads as a
    clean run. It now FAILS by default and can be waived only by an explicit
    opt-out, which is the actual fix. This test stays as the thing that
    notices if that polarity is quietly put back, and it pins the three facts
    that would otherwise make a silent skip invisible: the exact DSN variable
    NAME, the opt-out NAME, and how many live tests the module is supposed to
    contain. Deleting a test there, renaming either variable, or reverting the
    gate to an unconditional skip goes red here.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "test_pc_edition_rollover.py")
    src = open(path, encoding="utf-8").read()
    names = [ln.split("(")[0][len("def "):] for ln in src.splitlines()
             if ln.startswith("def test_")]
    assert len(names) == 10, (
        "test_pc_edition_rollover.py has %d live tests, expected 10. If that is "
        "deliberate, change the number here in the same commit -- do not delete "
        "this assertion, it is the only thing that notices. Found: %r"
        % (len(names), names))
    # AST, not substring. `'PC_EDITION_TEST_PG_OPTOUT' in src` is satisfied by
    # the COMMENT that explains the variable, so gutting the assignment to
    # `OPTOUT = False` left that check green -- measured, on this very guard,
    # which is why it now reads the parsed module instead of its text.
    tree = ast.parse(src)

    gate = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (isinstance(tgt, ast.Name) and tgt.id == "DSN_VAR"
                        and isinstance(node.value, ast.Constant)):
                    gate = node.value.value
    assert gate == "PC_EDITION_TEST_PG_DSN", (
        "the rollover module's DSN gate variable is %r, not the documented name; "
        "a caller exporting the documented name would get a clean run that "
        "collected nothing" % (gate,))

    # Module-level NAME = "literal", so `os.environ.get(DSN_VAR)` resolves to
    # the string it actually reads rather than being skipped as non-constant.
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    consts[tgt.id] = node.value.value

    env_reads = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "environ"
                and node.args):
            arg = node.args[0]
            if isinstance(arg, ast.Constant):
                env_reads.add(arg.value)
            elif isinstance(arg, ast.Name) and arg.id in consts:
                env_reads.add(consts[arg.id])
    assert "PC_EDITION_TEST_PG_OPTOUT" in env_reads, (
        "nothing in the module READS PC_EDITION_TEST_PG_OPTOUT, so either the "
        "waiver is gone (every machine without a cluster now fails, with no "
        "way to say so deliberately) or the gate has gone back to skipping by "
        "default. environ keys actually read: %r" % sorted(env_reads))
    assert gate in env_reads, (
        "the module declares DSN_VAR but never reads that environment variable")

    # THE POLARITY ITSELF, read out of the parsed module: the DSN gate's
    # refusal path must call pytest.fail, not pytest.skip. This is the one
    # assertion that distinguishes "coverage did not run and said so" from
    # "coverage did not run and the summary said exit 0", and it is the exact
    # revert that would otherwise be invisible from outside the module.
    gatefn = next((n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == "_require_live_pg"), None)
    assert gatefn is not None, (
        "test_pc_edition_rollover.py no longer defines _require_live_pg, so "
        "nothing forces a missing DSN to be reported at all")
    calls = {n.func.attr for n in ast.walk(gatefn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "pytest"}
    assert "fail" in calls, (
        "the rollover module's DSN gate no longer calls pytest.fail: a run "
        "without a cluster goes back to reporting a clean exit for ten tests "
        "that did not execute. pytest calls found in the gate: %r" % sorted(calls))
    assert "skip" in calls, (
        "the gate can no longer SKIP, so the deliberate waiver has no effect "
        "and a machine with no cluster cannot run the ordinary suite")



def test_the_mint_read_the_gated_module_copies_is_the_one_production_runs():
    """Bind that module's hand-copied mint read to production, OUTSIDE the gate.

    test_pc_edition_rollover.py holds a copy of the pack-open path's edition
    read, because production spells that read inline rather than as a module
    constant -- there is no symbol to import, so nothing fails loudly when the
    original changes. Something has to hold the copy to it, and that something
    cannot live inside the gate: on a machine with no DSN the whole module
    skips, and that is precisely where a copy drifts with nobody watching.

    The constant is lifted out of the sibling's SOURCE, not imported. This file
    already reads that file as text a few tests above, and importing it would
    run its module-level `raise` whenever PC_EDITION_TESTS_REQUIRED is set
    without a DSN -- turning a deliberate verification run into a collection
    error in an unrelated file.

    Exact count, not `in`: a read matching twice means two mint paths, and
    pinning one says nothing about the other (#521).
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "test_pc_edition_rollover.py")
    sibling = open(path, encoding="utf-8").read()

    copied = None
    for node in ast.walk(ast.parse(sibling)):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MINT_READ"
                for t in node.targets):
            copied = ast.literal_eval(node.value)
    assert isinstance(copied, str) and copied, (
        "test_pc_edition_rollover.py no longer assigns a string to MINT_READ, "
        "so its rollover-versus-mint tests are either gone or describing a "
        "statement this guard can no longer see. Found: %r" % (copied,))

    src = open(main.__file__, encoding="utf-8", newline="").read()
    hits = src.count(copied)
    assert hits == 1, (
        "the mint path's edition read appears %d times in main.py, expected "
        "exactly 1. The copy in test_pc_edition_rollover.py is:\n  %s\n"
        "If production changed, update that copy and re-check the rollover "
        "tests there still describe what production does. If it now appears "
        "twice, there are two mint paths and only one of them is pinned."
        % (hits, copied))
