"""The janitor SQL self-test walker (main._janitor_sql_from_sources), run
statically. The live inventory must have no `dynamic` site — each one is a
synthetic self-test FAILURE at boot — the Player Cards janitor steps must be
in the reachable set, and module-level constants resolve under exactly the
rules the walker documents (Sept 10 batch, walker r10)."""
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
            "_pc_grant_earned_packs", "_podium_player_ids", "_publish_pair_sitting"} <= funcs
    sqls = [" ".join(s["sql"].split()) for s in inv["statements"]]
    assert sum("rs.winner_id AS w1" in q for q in sqls) == 1
    assert sum("UPDATE pc_packs p SET status = 'voided'" in q for q in sqls) == 4
    assert sum("INSERT INTO pc_packs (player_id, source, mode, kind, reference_id, status)" in q for q in sqls) == 1
    assert any("pg_advisory_xact_lock(hashtext('dcpair:'" in q for q in sqls)
    # the podium statements bind the active window; no query interpolates the env int
    assert any("make_interval(days => CAST(:active_days AS integer))" in q for q in sqls)
    assert not any("make_interval(days => 90)" in q for q in sqls)


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
