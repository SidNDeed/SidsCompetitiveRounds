"""The /health word that says this build credits the title ladder.

The ladder-hook batch (v1.41.0 item 12, server half) adds no route and no key
to any GET answer both builds serve: the title-ladder route answers on the
build before it, from the same tables, and a credit is written only inside a
rated completion. So `ladder_hook` was the release train's build discriminator
for that batch -- absent on the build before it, 4 on it, on both roles. The
title ladders build (board row 29) moved the credit to one per ranked GAME at
the three game-reporting paths, so the word reads 3 from that build on; that
build's own discriminator is its `title_ladders` word.

The value is DERIVED (#342): how many of the three ranked game-reporting
functions (test_title_ladders.COMPLETION_SITES) load the hook's name,
record_completed_games, in their own compiled code. A literal 3 would read 3
on a build that had lost a site's call, which is the deploy this word exists
to tell apart. It is read from code objects, so a comment or a docstring
naming the hook cannot move it. The count is title_ladders.hooked_site_count,
beside the hook, and the name it counts is read off the hook function, so
main.py names the hook at its three awaited calls and nowhere else -- the
whole-file test in test_title_ladders.py holds main.py to that, and it is
what refused this word's first form, a helper in main.py that typed the name
as a string. The controls compile the real functions again in-process with
one call taken out (2), and probes that name the hook only in prose (0); the
health arms are checked with the constant moved.
"""
import ast
import copy
import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

from test_player_cards_server import _run                        # noqa: E402
from test_title_ladders import COMPLETION_SITES, HOOK            # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402
import title_ladders                                             # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
TL_PY = pathlib.Path(title_ladders.__file__).resolve()
COUNT = "hooked_site_count"
_TREE = []


class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _health():
    """(connected answer, degraded answer) as the response model renders them."""
    return (_run(main.health_check(db=_Up())).model_dump(),
            _run(main.health_check(db=_Down())).model_dump())


def _module_tree():
    """main.py's parse tree, parsed once; callers that change it copy first."""
    if not _TREE:
        _TREE.append(ast.parse(MAIN_PY.read_text(encoding="utf-8")))
    return _TREE[0]


def _binding(tree, name):
    assigns = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    assert len(assigns) == 1, (name, len(assigns))
    return assigns[0]


def _without_the_call(name):
    """main.<name> compiled from main.py's own source with its one awaited
    hook call replaced by `pass` -- nothing else changed -- over main's
    globals as they are now."""
    fn = copy.deepcopy(next(
        n for n in _module_tree().body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name))
    removed = []

    class _Drop(ast.NodeTransformer):
        def visit_Expr(self, node):
            v = node.value
            if (isinstance(v, ast.Await) and isinstance(v.value, ast.Call)
                    and isinstance(v.value.func, ast.Attribute) and v.value.func.attr == HOOK):
                removed.append(node.lineno)
                return ast.copy_location(ast.Pass(), node)
            return node
    _Drop().visit(fn)
    assert len(removed) == 1, (name, removed)
    fn.decorator_list = []
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(vars(main))
    exec(compile(module, "%s [%s without its hook call]" % (MAIN_PY, name), "exec"), namespace)
    return namespace[name]


def test_the_marker_is_derived_from_the_three_sites_and_reads_3_here():
    """Derived, bound once, over exactly the three sites, and 3 at this tip.

    The binding has to be a CALL of the count with no number anywhere in
    it, over a tuple naming exactly COMPLETION_SITES' three functions, and
    nothing may rebind either name afterwards. The name the count looks for
    is the hook's own, read off the function in title_ladders.py rather than
    typed there a second time."""
    tree = _module_tree()
    for name in ("_LADDER_HOOK", "_LADDER_HOOK_SITES"):
        stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
                  and n.id == name and isinstance(n.ctx, ast.Store)]
        assert len(stores) == 1, (name, len(stores))
    value = _binding(tree, "_LADDER_HOOK").value
    assert isinstance(value, ast.Call), ast.dump(value)
    assert not [n for n in ast.walk(value)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, bool))]
    assert ast.unparse(value) == "title_ladders.%s(_LADDER_HOOK_SITES)" % COUNT, (
        ast.unparse(value))
    sites = _binding(tree, "_LADDER_HOOK_SITES").value
    assert isinstance(sites, ast.Tuple), ast.dump(sites)
    names = [ast.unparse(e) for e in sites.elts]
    assert sorted(names) == sorted(COMPLETION_SITES.values()), names
    assert main._LADDER_HOOK_SITES == tuple(getattr(main, n) for n in names)
    for fn in main._LADDER_HOOK_SITES:
        assert HOOK in fn.__code__.co_names, fn.__name__
    assert main._LADDER_HOOK == 3
    assert title_ladders.hooked_site_count(main._LADDER_HOOK_SITES) == 3

    tl_tree = ast.parse(TL_PY.read_text(encoding="utf-8"))
    hook_name = _binding(tl_tree, "_HOOK_NAME")
    assert ast.unparse(hook_name.value) == HOOK + ".__name__", ast.unparse(hook_name.value)
    assert title_ladders._HOOK_NAME == HOOK


def test_the_derivation_counts_each_hooked_site_and_nothing_beside_it():
    """Each real site with its call taken out reads 2 beside the other two;
    the unhooked 1v2 endpoint, the unhooked 2v2 settlement and an empty set
    read 0; a probe naming the hook in a docstring, a comment and a getattr
    string reads 0, and one that calls it reads 1."""
    count = title_ladders.hooked_site_count
    three = main._LADDER_HOOK_SITES
    assert count(three) == 3
    for name in COMPLETION_SITES.values():
        variant = _without_the_call(name)
        assert HOOK not in variant.__code__.co_names, name
        rest = tuple(fn for fn in three if fn.__name__ != name)
        assert len(rest) == 2, name
        assert count(rest + (variant,)) == 2, name
    assert count((main.submit_ovt_match,)) == 0
    assert count((main._complete_team_series_with_ratings,)) == 0
    assert count(()) == 0

    def probe(source):
        namespace = {}
        exec(compile(source, "<marker-probe>", "exec"), namespace)
        return namespace["f"]
    prose = probe(
        "async def f(db, tl):\n"
        "    '''Calls tl.record_completed_games once per completion.'''\n"
        "    # await tl.record_completed_games(db, [], mode='1v1', reference_id='x')\n"
        "    return getattr(tl, 'record_completed_games')\n")
    assert count((prose,)) == 0
    called = probe(
        "async def f(db, tl):\n"
        "    await tl.record_completed_games(db, [], mode='1v1', reference_id='x')\n")
    assert count((called,)) == 1


def test_both_health_arms_report_the_constant(monkeypatch):
    """ok AND degraded, and what they report is the constant, not a 3 typed
    beside it: moved to 0, both answers move with it."""
    up, down = _health()
    assert (up["status"], down["status"]) == ("ok", "degraded")
    assert (up["ladder_hook"], down["ladder_hook"]) == (3, 3)
    monkeypatch.setattr(main, "_LADDER_HOOK", 0)
    up0, down0 = _health()
    assert (up0["ladder_hook"], down0["ladder_hook"]) == (0, 0)


def test_the_marker_is_declared_and_read_by_nothing_else():
    """Declared on the model without a default, passed in exactly the two
    arms, read nowhere else, and the count called by the binding alone.

    HealthResponse drops what it does not declare, so the handler passing
    the word is not by itself enough; the negative control is a name that is
    NOT declared and must be missing from the same dump (#306)."""
    field = schemas.HealthResponse.model_fields.get("ladder_hook")
    assert field is not None and field.annotation is int and field.is_required()
    up, _ = _health()
    assert "ladder_hook" in up
    assert "ladder_hook_not_a_field" not in schemas.HealthResponse.model_fields
    assert "ladder_hook_not_a_field" not in up

    tree = _module_tree()
    health = [n for n in tree.body
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    assert len(health) == 1, len(health)
    tries = [n for n in ast.walk(health[0]) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}

    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_LADDER_HOOK" and isinstance(n.ctx, ast.Load)]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1

    keywords = [k for k in ast.walk(tree)
                if isinstance(k, ast.keyword) and k.arg == "ladder_hook"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == "_LADDER_HOOK" for k in keywords)

    inside = {id(n) for n in ast.walk(_binding(tree, "_LADDER_HOOK").value)}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == COUNT]
    assert len(calls) == 1 and id(calls[0]) in inside, len(calls)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == COUNT]
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.alias)
                and COUNT in (n.name.split(".")[-1], n.asname)]
    sites = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_LADDER_HOOK_SITES" and isinstance(n.ctx, ast.Load)]
    assert len(sites) == 1 and id(sites[0]) in inside, len(sites)
