"""B4 / B3 answers that need no database (the live ones are in
test_ban_expiry_live.py): what the ban request admits, the hover card's
profile block key order, and the bot's end line on the #scr-admin post."""
import ast
import os
from datetime import datetime, timezone

import pydantic
import pytest

import main
import schemas

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.normpath(os.path.join(HERE, "..", "discord_bot.py"))


def _req(**fields):
    return main._AdminBanReq(admin_steam_id="1", target_steam_id="2", **fields)


@pytest.mark.parametrize("bad", [0, -1, main.BAN_DURATION_MAX_MINUTES + 1, "60", True, 1.0, [1]])
def test_a_length_that_is_not_a_whole_number_of_minutes_in_range_is_refused(bad):
    with pytest.raises(pydantic.ValidationError) as refused:
        _req(duration_minutes=bad)
    assert [e["loc"] for e in refused.value.errors()] == [("duration_minutes",)], refused.value.errors()


def test_the_length_bounds_and_whether_it_was_sent():
    # the cap ruling (16 Nov 2026): 8760 hours, models.BAN_MAX_MINUTES
    assert main.BAN_DURATION_MAX_MINUTES == 365 * 24 * 60 == main.BAN_MAX_MINUTES
    for ok in (1, 60, main.BAN_DURATION_MAX_MINUTES):
        assert _req(duration_minutes=ok).duration_minutes == ok
    # the 1.41.0 request carries no field: the maximum, and not a length change
    old = _req()
    assert old.duration_minutes is None and "duration_minutes" not in old.model_fields_set
    # an explicit null is SENT: it sets an active ban's end to its start plus the maximum
    null = _req(duration_minutes=None)
    assert null.duration_minutes is None and "duration_minutes" in null.model_fields_set
    # the signature's canonical string does not move (admin:{admin}:ban:{target})
    import inspect
    src = inspect.getsource(main.admin_ban)
    assert '_require_admin(db, req.admin_steam_id, "ban", req.target_steam_id, req.hmac_signature)' in src


def test_the_profile_block_keeps_its_keys_and_adds_is_banned_last():
    assert list(schemas.H2HProfileBlock.model_fields) == [
        "display_name", "title", "title_color", "tier", "tier_color", "rating_1v1", "rd_1v1",
        "level", "is_online", "last_seen_s", "is_banned"]
    dumped = schemas.H2HProfileBlock(is_banned=True).model_dump()
    assert list(dumped)[-1] == "is_banned" and dumped["is_banned"] is True
    assert schemas.H2HProfileBlock().is_banned is False


def _bot_function(name):
    with open(BOT, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    (fn,) = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    return fn


def _bot_assign(name):
    with open(BOT, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    (node,) = [n for n in tree.body if isinstance(n, ast.Assign)
               and [ast.unparse(t) for t in n.targets] == [name]]
    return node


def _end_line():
    ns = {"datetime": datetime}
    body = [_bot_assign("_BAN_END_LINE_UNREAD"), _bot_function("_ban_end_line")]
    exec(compile(ast.Module(body=body, type_ignores=[]), BOT, "exec"), ns)
    return ns["_ban_end_line"]


def test_the_bot_end_line_always_carries_an_end_and_never_raises():
    """The cap ruling (16 Nov 2026): every ban ends, so every notice carries
    its end line: the end itself, or, for a row whose end the bot cannot
    read, the line that says a ban ends within a year. Never empty."""
    line = _end_line()
    end = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert line({"expires_at": "2031-01-02T03:04:05Z"}) == "Ends: <t:%d:F>" % int(end.timestamp())
    unread = "Ends: **within one year of the ban** (end not readable)"
    for odd in ({"expires_at": None}, {"id": "x"}, {"expires_at": "not a time"},
                {"expires_at": 12}, None, "row"):
        assert line(odd) == unread, odd
    with open(BOT, encoding="utf-8") as fh:
        src = fh.read()
    assert "Permanent" not in ast.unparse(_bot_function("_ban_end_line")) and "**Permanent**" not in src


def test_the_end_line_is_built_inside_the_post_and_never_reaches_the_ban():
    """Lesson 187: the post is optional. The line is built in the per-ban try
    of poll_new_bans (whose failure is logged and skipped), after the ban is
    already written by the api; _ban_end_line itself swallows every error."""
    poll = _bot_function("poll_new_bans")
    (loop,) = [n for n in ast.walk(poll) if isinstance(n, ast.For)]
    (tried,) = [n for n in loop.body if isinstance(n, ast.Try)]
    body = ast.unparse(ast.Module(body=tried.body, type_ignores=[]))
    assert body.index("end_line = _ban_end_line(b)") < body.index("discord.Embed(")
    fn = _bot_function("_ban_end_line")
    assert isinstance(fn.body[-1], ast.Try) and [ast.unparse(h.type) for h in fn.body[-1].handlers] == ["Exception"]
    # the helper sits above the poller without taking its decorator: the
    # poller is still the 60 s task the bot starts, the helper a plain function
    assert [ast.unparse(d) for d in poll.decorator_list] == ["tasks.loop(seconds=60)"]
    assert fn.decorator_list == [] and isinstance(fn, ast.FunctionDef)


# -- F2 (fix 1): no per-process ban state ------------------------------------
#
# A ban answer is the database's current word or nothing: no function that
# reads player_bans keeps state between calls. Derived, not listed: every
# function the definition census (test_ban_active_definition.scan_tree) finds
# reading player_bans, and every function that calls one by name, is walked
# for each way a function keeps state past its own call (_state_writes). The
# only module-level names about bans that hold state at all are the bot's
# feed cursor, which is not ban state: it is the id of the last ban POSTED,
# so an ended ban never changes it and it decides no answer. Each walk has a
# planted control that it must report.
MUTATORS = {"add", "update", "clear", "discard", "remove", "append", "extend", "pop", "popitem",
            "setdefault", "insert", "appendleft", "__setitem__"}
CACHE_DECORATORS = {"lru_cache", "cache", "cached", "cached_property", "alru_cache"}
CONTAINERS = {"set", "dict", "list", "deque", "defaultdict", "OrderedDict", "Counter"}
BAN_STATE_ALLOWED = {
    ("discord_bot.py", "_last_ban_id_posted"): "the feed cursor: the id of the last ban posted to #scr-admin",
    ("discord_bot.py", "_ban_poller_initialized"): "whether the feed cursor has been seeded at start",
}
# A module-level container about bans that is a CONSTANT, not state. The
# detector above reports it (it is a top-level container); a row here is
# accepted only when _constant_problems proves it, from the syntax of every
# module the definition census reads, and finds no problem:
#   1. the name is bound exactly once in its module, at the top level, by a
#      plain assignment to a display of a closed shape (a dict whose values
#      are all constants, or all dict displays of the same closed shape);
#   2. no `global` or `nonlocal` names it in any module read;
#   3. every other occurrence (the bare name in its module, `M.NAME` in
#      another module where M is bound to its module by an import) is a read
#      of a closed shape that yields only a constant leaf, a key, a bool or an
#      int; a store or del through a subscript at any depth, any other method
#      call, a read that hands out an inner dict, and the name or a part of it
#      assigned, passed, returned, yielded or put into a container are each a
#      problem that names its line, and so is importing the name itself;
#   4. in a function where the name is a parameter or is bound, every
#      occurrence is a problem (a shadow);
#   5. setattr, delattr or getattr with the name's string, and a subscript of
#      globals() or vars(...) with it, anywhere in the modules read, is a
#      problem.
# LIMITS, each a sentence that can be false: the check reads syntax only, so a
# store through a name built from a computed string (setattr(m, "BAN_" + x)),
# a store made by a module the census does not read (backend/api/*.py and
# discord_bot.py are read; tests and scripts are not), a test's replacement
# of the attribute for its own run (test_ban_sweep_live.py does that with
# monkeypatch), and a store through an object reached by a route the shapes
# do not name (sys.modules, a module object passed around) are not seen.
BAN_CONSTANTS_PROVEN = {
    ("main.py", "BAN_RECORD_STATUSES"):
        "the class of every status word each record table is written with (live, open_lobby, terminal)",
}


def _module_trees():
    import test_ban_active_definition as census
    out = {}
    for name, path in census._modules():
        with open(path, encoding="utf-8") as fh:
            out[name] = ast.parse(fh.read())
    return out


def _functions(tree):
    out = {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = prefix + [child.name]
                if not isinstance(child, ast.ClassDef):
                    out[".".join(q)] = child
                visit(child, q)
            else:
                visit(child, prefix)
    visit(tree, [])
    return out


def _module_names(tree):
    """The names a module binds at its top level by assignment."""
    return {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}


def _state_writes(fn, module_names):
    """Every way fn keeps state past its own call that this walk knows: a
    caching decorator on fn; a `global` / `nonlocal`; and, on a module-level
    name, a mutating call, a subscript or attribute store, or a setattr."""
    hits = []
    for d in fn.decorator_list:
        f = d.func if isinstance(d, ast.Call) else d
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name in CACHE_DECORATORS:
            hits.append(("cached", d.lineno, name))
    for n in ast.walk(fn):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            hits.append(("global", n.lineno, tuple(n.names)))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS \
                and isinstance(n.func.value, ast.Name) and n.func.value.id in module_names:
            hits.append(("mutates", n.lineno, n.func.value.id))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "setattr" \
                and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id in module_names:
            hits.append(("stores", n.lineno, n.args[0].id))
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, (ast.Subscript, ast.Attribute)) and isinstance(t.value, ast.Name) \
                        and t.value.id in module_names:
                    hits.append(("stores", n.lineno, t.value.id))
    return hits


# A caller of a reader that keeps state: allowed only with its reason (it
# must decide no answer).
CALLER_STATE_ALLOWED = {
    ("main.py", "_h2h_card_blocks", "_h2h_card_last_warn"):
        "a log throttle: when the last failure warning was printed; it decides no answer",
}


def _walk_set(sources=None):
    """Every function the census finds reading player_bans, plus every
    function that calls one of them by name (one hop: a caller that caches a
    reader's answer is the same class). `sources` (module -> text) replaces
    the tree for the controls."""
    import test_ban_active_definition as census
    if sources is None:
        readers, _orm = census.scan_tree()
        trees = _module_trees()
    else:
        readers, trees = {}, {}
        for module, src in sources.items():
            readers.update(census.scan_source(module, src)[0])
            trees[module] = ast.parse(src)
    walk = {}
    for (module, qual) in readers:
        if qual == "<module>" or (module, qual) == ("models.py", "PlayerBan"):
            continue   # module constants (no state of their own) and the model's __tablename__
        fn = _functions(trees[module]).get(qual)
        assert fn is not None, (module, qual)
        walk[(module, qual)] = ("reader", fn)
    for module, tree in trees.items():
        names = {q.split(".")[-1] for (m, q) in walk if m == module}
        for qual, fn in _functions(tree).items():
            if (module, qual) in walk:
                continue
            calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            if calls & names:
                walk[(module, qual)] = ("caller", fn)
    return walk, trees


def _reader_state_problems(walk, trees):
    problems = []
    for (module, qual), (_kind, fn) in sorted(walk.items()):
        for hit in _state_writes(fn, _module_names(trees[module])):
            names = hit[2] if isinstance(hit[2], tuple) else (hit[2],)
            if not all((module, qual, x) in CALLER_STATE_ALLOWED for x in names):
                problems.append((module, qual, hit))
    return problems


def _module_ban_state(trees):
    """Every module-level name whose words include ban/bans/banned that is
    state, not a constant: rebound anywhere (a `global` / `nonlocal` of it),
    or bound at the top level to a mutable container."""
    found = set()
    for module, tree in trees.items():
        banish = {x for x in _module_names(tree) if {"ban", "bans", "banned"} & set(x.lower().strip("_").split("_"))}
        for n in ast.walk(tree):
            if isinstance(n, (ast.Global, ast.Nonlocal)):
                found.update((module, x) for x in n.names if x in banish)
        for n in tree.body:   # a module-level mutable container is state even without a global
            if not isinstance(n, (ast.Assign, ast.AnnAssign)) or n.value is None:
                continue
            v = n.value
            if isinstance(v, (ast.Set, ast.Dict, ast.List)) or (
                    isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in CONTAINERS):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                found.update((module, t.id) for t in targets if isinstance(t, ast.Name) and t.id in banish)
    return found


_KEY_CALLS = {"sorted", "list", "set", "tuple", "frozenset"}
_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _display_depth(v):
    """The nesting depth of a closed display (a dict of constants is 1, a
    dict of such dicts 2, ...), or None when the value is not one."""
    if not isinstance(v, ast.Dict) or not v.keys or any(k is None or not isinstance(k, ast.Constant) for k in v.keys):
        return None
    if all(isinstance(x, ast.Constant) for x in v.values):
        return 1
    inner = {_display_depth(x) for x in v.values}
    if len(inner) == 1 and None not in inner:
        return inner.pop() + 1
    return None


def _parents(tree):
    up = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            up[c] = n
    return up


def _enclosing(node, up):
    """The innermost function holding node, or None at the module level."""
    n = up.get(node)
    while n is not None and not isinstance(n, _FUNCS):
        n = up.get(n)
    return n


def _qual(fn, up):
    names = []
    while fn is not None:
        names.append(getattr(fn, "name", "<lambda>"))
        fn = _enclosing(fn, up)
    return ".".join(reversed(names)) or "<module>"


def _top_level_bindings(tree, name):
    """Every binding of `name` in the module's own scope: the module body and
    every compound statement in it, not the bodies of defs and classes."""
    out = []
    stack = list(tree.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.name == name:
                out.append(n)
            stack.extend(n.decorator_list)
            continue
        if isinstance(n, ast.Lambda):
            continue
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.append(n)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out.extend(n for a in n.names if (a.asname or a.name.split(".")[0]) == name)
        elif isinstance(n, ast.ExceptHandler) and n.name == name:
            out.append(n)
        stack.extend(ast.iter_child_nodes(n))
    return out


def _constant_problems(trees, module, name):
    """(problems, reads) for the row (module, name): every reason the name is
    NOT proven a constant, each (word, module, line, text), and every read
    the walk examined, each (module, function, line, shape)."""
    problems, reads = [], []
    home = trees[module]
    stem = module[:-3]

    def bad(word, mod, node, text=""):
        problems.append((word, mod, getattr(node, "lineno", 0), text or name))

    # 1. one top-level binding, a plain assignment of a closed display
    binds = sorted(_top_level_bindings(home, name), key=lambda b: (b.lineno, b.col_offset))
    depth, the_target = None, None
    if not binds:
        problems.append(("binding", module, 0, "no top-level binding"))
    for b in binds[1:]:
        bad("binding", module, b, "a second top-level binding")
    if len(binds) == 1:
        b = binds[0]
        st = _parents(home).get(b) if isinstance(b, ast.Name) else b
        if isinstance(st, ast.Assign) and st in home.body and st.targets == [b]:
            the_target = b
            depth = _display_depth(st.value)
            if depth is None:
                bad("not_display", module, st, "the value is not a closed display")
        else:
            bad("binding", module, b, "not a plain top-level assignment")
    depth = depth or 1

    for mod, tree in sorted(trees.items()):
        up = _parents(tree)
        # 2. global / nonlocal; 5. the name's string in setattr & co
        aliases = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Global, ast.Nonlocal)) and name in n.names:
                bad("global", mod, n)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in ("setattr", "delattr", "getattr") \
                    and any(isinstance(a, ast.Constant) and a.value == name for a in n.args):
                bad(n.func.id, mod, n)
            elif isinstance(n, ast.Subscript) and isinstance(n.value, ast.Call) \
                    and isinstance(n.value.func, ast.Name) and n.value.func.id in ("globals", "vars") \
                    and isinstance(n.slice, ast.Constant) and n.slice.value == name:
                bad("globals", mod, n)
            elif isinstance(n, ast.Import) and mod != module:
                aliases.update(a.asname or a.name for a in n.names if a.name == stem)
            elif isinstance(n, ast.ImportFrom) and mod != module:
                if n.module == stem and any(a.name == name for a in n.names):
                    bad("import", mod, n)
                if n.module in (None, "") or n.module == ".":
                    aliases.update(a.asname or a.name for a in n.names if a.name == stem)
                if n.module == stem and any(a.name == "*" for a in n.names):
                    bad("import", mod, n, "import *")
        # the occurrences
        occ = []
        for n in ast.walk(tree):
            if mod == module and isinstance(n, ast.Name) and n.id == name and n is not the_target:
                occ.append(n)
            elif mod != module and isinstance(n, ast.Attribute) and n.attr == name \
                    and isinstance(n.value, ast.Name) and n.value.id in aliases:
                occ.append(n)
        # 4. the shadows: a function where the name is a parameter or bound
        shadows = set()
        if mod == module:
            for fn in ast.walk(tree):
                if not isinstance(fn, _FUNCS):
                    continue
                a = fn.args
                params = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
                params |= {x.arg for x in (a.vararg, a.kwarg) if x is not None}
                stored = any(isinstance(x, ast.Name) and x.id == name and isinstance(x.ctx, (ast.Store, ast.Del))
                             for x in ast.walk(fn))
                if name in params or stored:
                    shadows.add(fn)
        for o in occ:
            fn = _enclosing(o, up)
            where = _qual(fn, up)
            f = fn
            shadowed = False
            while f is not None:
                if f in shadows:
                    shadowed = True
                f = _enclosing(f, up)
            if shadowed:
                bad("shadow", mod, o, where)
                continue
            word, shape = _read_shape(o, up, depth)
            if word is None:
                reads.append((mod, where, o.lineno, shape))
            else:
                bad(word, mod, o, "%s in %s" % (shape, where))
    return problems, reads


def _read_shape(o, up, depth):
    """(None, shape) for a closed read of occurrence o, else (word, shape)."""
    if isinstance(o.ctx, ast.Store):
        return "binding", "rebound"
    if isinstance(o.ctx, ast.Del):
        return "del", "del"
    node, level = o, 0
    while True:
        p = up.get(node)
        if isinstance(p, ast.Subscript) and p.value is node:
            if isinstance(p.ctx, ast.Store):
                return "store", "store at depth %d" % (level + 1)
            if isinstance(p.ctx, ast.Del):
                return "del", "del at depth %d" % (level + 1)
            level += 1
            node = p
            if level == depth:
                g = up.get(node)
                if isinstance(g, ast.AugAssign) and g.target is node:
                    return "augmented", "augmented store at depth %d" % level
                return None, "leaf at depth %d" % level
            continue
        break
    p = up.get(node)
    path = "N" + "[e]" * level
    if isinstance(p, ast.AugAssign) and p.target is node:
        return "augmented", path + " augmented"
    if isinstance(p, ast.Attribute) and p.value is node:
        g = up.get(p)
        if isinstance(g, ast.Call) and g.func is p:
            m = p.attr
            if m == "keys" and not g.args and not g.keywords:
                return None, path + ".keys()"
            if m in ("items", "values", "get") and level == depth - 1:
                return None, "%s.%s()" % (path, m)
            if m in ("items", "values", "get"):
                return "inner", "%s.%s() hands out an inner dict" % (path, m)
            return ("mutator" if m in MUTATORS else "call"), "%s.%s()" % (path, m)
        if isinstance(p.ctx, (ast.Store, ast.Del)):
            return "store", path + "." + p.attr + " stored"
        return "attribute", path + "." + p.attr
    if isinstance(p, ast.Compare) and node in p.comparators:
        i = p.comparators.index(node)
        if isinstance(p.ops[i], (ast.In, ast.NotIn)):
            return None, "e in " + path
    if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.args == [node] and not p.keywords:
        if p.func.id == "len":
            return None, "len(%s)" % path
        if level == 0 and p.func.id in _KEY_CALLS:
            return None, "%s(N)" % p.func.id
    if level == 0 and isinstance(p, (ast.For, ast.AsyncFor)) and p.iter is node:
        return None, "for over N"
    if level == 0 and isinstance(p, ast.comprehension) and p.iter is node:
        return None, "comprehension over N"
    if isinstance(p, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and p.value is node:
        return "alias", path + " assigned"
    if isinstance(p, ast.Call):
        return "passed", path + " passed to a call"
    if isinstance(p, ast.Return):
        return "returned", path + " returned"
    if isinstance(p, (ast.Yield, ast.YieldFrom)):
        return "yielded", path + " yielded"
    if isinstance(p, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.Starred)):
        return "contained", path + " put into a container"
    return "other", "%s under %s" % (path, type(p).__name__)


def test_no_reader_of_player_bans_keeps_state_between_calls():
    walk, trees = _walk_set()
    problems = _reader_state_problems(walk, trees)
    assert not problems, problems
    kinds = [k for k, _ in walk.values()]
    print("[ban-state] readers %d callers %d" % (kinds.count("reader"), kinds.count("caller")))
    # the walk reached the readers it must (no silent empty walk): the ping's
    # ban read, the one-row check, the tournaments check, and their callers
    for must in [("main.py", "_presence_online_ids_shown"), ("main.py", "_is_banned"),
                 ("tournaments.py", "_player_id_banned"), ("main.py", "presence_ping"),
                 ("main.py", "queue_count")]:
        assert must in walk, must
    # every allowed caller state is still there (an allow-list row cannot go stale)
    for (module, qual, name) in CALLER_STATE_ALLOWED:
        assert (module, qual) in walk, (module, qual)
    # the fallback set the r1 build kept is gone, and nothing replaced it
    src = open(os.path.join(HERE, "..", "api", "main.py"), encoding="utf-8").read()
    assert "_presence_banned_last" not in src and "_presence_online_count_shown_fallback" not in src


def test_the_only_module_level_ban_state_is_the_bots_feed_cursor():
    """The detector's finds, less the rows proven constants, are the feed
    cursor's two names. A proven row must still be found (it cannot go
    stale), must have no problem, and its walk must have examined the
    product's one read of it (no silent empty walk)."""
    trees = _module_trees()
    found = _module_ban_state(trees)
    for (module, name) in BAN_CONSTANTS_PROVEN:
        assert (module, name) in found, ("a proven constant the detector no longer finds", module, name)
        problems, reads = _constant_problems(trees, module, name)
        assert not problems, (module, name, problems)
        assert reads, (module, name, "no read examined")
    _p, reads = _constant_problems(trees, "main.py", "BAN_RECORD_STATUSES")
    assert ("main.py", "_ban_live_statuses_sql") in {(m, f) for m, f, _l, _s in reads}, reads
    assert found - set(BAN_CONSTANTS_PROVEN) == set(BAN_STATE_ALLOWED), (sorted(found), sorted(BAN_STATE_ALLOWED))


PLANTED_STATE = '''
_banned_seen = set()
_last_ban_answer = None
_ban_snapshot: dict = {}
_ban_holder = SimpleNamespace(last=None)


async def planted_reader(db):
    global _last_ban_answer
    rows = await db.execute(text("SELECT steam_id FROM player_bans b WHERE " + player_ban_active_sql("b")))
    _banned_seen.add(1)
    _last_ban_answer = rows
    return rows


async def planted_caller(db):
    rows = await planted_reader(db)
    _ban_snapshot["rows"] = rows
    _ban_holder.last = rows
    _banned_seen.update(rows)
    return rows


@lru_cache(maxsize=1)
def planted_cached(db):
    return db.execute(text("SELECT 1 FROM player_bans b WHERE " + player_ban_active_sql("b")))


async def planted_clean(db):
    return await db.execute(text("SELECT 1 FROM player_bans b WHERE " + player_ban_active_sql("b")))


async def planted_unrelated(db):
    _banned_seen.add(2)
'''


def test_control_a_reader_or_caller_that_keeps_ban_state_is_reported():
    """Each way of keeping state, planted in a reader, a caller and a cached
    reader, is reported by name; a clean reader is walked and is silent; a
    function that neither reads player_bans nor calls a reader is not walked."""
    walk, trees = _walk_set({"planted.py": PLANTED_STATE})
    assert {q: k for (_m, q), (k, _fn) in walk.items()} == {
        "planted_reader": "reader", "planted_cached": "reader", "planted_clean": "reader",
        "planted_caller": "caller"}, sorted(walk)
    got = sorted((q, hit[0], hit[2]) for _m, q, hit in _reader_state_problems(walk, trees))
    assert got == [
        ("planted_cached", "cached", "lru_cache"),
        ("planted_caller", "mutates", "_banned_seen"),
        ("planted_caller", "stores", "_ban_holder"),
        ("planted_caller", "stores", "_ban_snapshot"),
        ("planted_reader", "global", ("_last_ban_answer",)),
        ("planted_reader", "mutates", "_banned_seen"),
    ], got


def test_control_module_level_ban_state_is_found():
    """A container bound at the top level (by = and by an annotated =) and a
    name rebound through `global` are found; a name only read is not."""
    found = _module_ban_state({"planted.py": ast.parse(PLANTED_STATE)})
    assert found == {("planted.py", "_banned_seen"), ("planted.py", "_ban_snapshot"),
                     ("planted.py", "_last_ban_answer")}, sorted(found)


# The constant proof's planted controls: the clean module below holds the
# product's own read shape; each control adds lines to it (or a second module
# that imports it), and the line marked `# PLANT` must be reported with the
# control's own reason word.
PLANTED_CONST = '''BAN_RECORD_STATUSES = {
    "team_series": {"active": "live", "completed": "terminal"},
    "ovt_series": {"active": "live", "canceled": "terminal"},
}


def _live(table):
    return sorted(w for w, c in BAN_RECORD_STATUSES[table].items() if c == "live")
'''
CONST_CONTROLS = {
    "subscript_store": ("store", "def f():\n    BAN_RECORD_STATUSES['x'] = {}  # PLANT\n", None),
    "nested_store": ("store", "def f():\n    BAN_RECORD_STATUSES['x']['a'] = 'live'  # PLANT\n", None),
    "mutator_on_name": ("mutator", "def f():\n    BAN_RECORD_STATUSES.update({})  # PLANT\n", None),
    "mutator_on_part": ("mutator", "def f():\n    BAN_RECORD_STATUSES['x'].update({})  # PLANT\n", None),
    "items_in_loop": ("inner", "def f():\n    for k, v in BAN_RECORD_STATUSES.items():  # PLANT\n"
                               "        print(k)\n", None),
    "whole_assigned": ("alias", "def f():\n    t = BAN_RECORD_STATUSES  # PLANT\n    return 0\n", None),
    "part_assigned": ("alias", "def f():\n    t = BAN_RECORD_STATUSES['x']  # PLANT\n    return 0\n", None),
    "whole_passed": ("passed", "def f():\n    print(BAN_RECORD_STATUSES)  # PLANT\n", None),
    "global_rebind": ("global", "def f():\n    global BAN_RECORD_STATUSES  # PLANT\n"
                                "    BAN_RECORD_STATUSES = {}\n", None),
    "second_binding": ("binding", "BAN_RECORD_STATUSES = {}  # PLANT\n", None),
    "store_through_alias": ("store", None, "import main\n\n\ndef g():\n"
                                           "    main.BAN_RECORD_STATUSES['x']['a'] = 'live'  # PLANT\n"),
    "setattr_string": ("setattr", None, "import main\n\n\ndef g():\n"
                                        "    setattr(main, 'BAN_RECORD_STATUSES', {})  # PLANT\n"),
    "del_part": ("del", "def f():\n    del BAN_RECORD_STATUSES['x']  # PLANT\n", None),
    "shadow_parameter": ("shadow", "def f(BAN_RECORD_STATUSES):\n"
                                   "    return BAN_RECORD_STATUSES['x']['a']  # PLANT\n", None),
}


def _plant_line(src):
    return [i for i, ln in enumerate(src.splitlines(), 1) if "# PLANT" in ln]


@pytest.mark.parametrize("control", sorted(CONST_CONTROLS))
def test_control_each_way_a_constant_could_be_state_is_reported(control):
    """Each control is reported at its planted line by its own reason word."""
    word, home_add, other = CONST_CONTROLS[control]
    home = PLANTED_CONST + ("\n\n" + home_add if home_add else "")
    trees = {"main.py": ast.parse(home)}
    mod, src = ("main.py", home)
    if other is not None:
        trees["other.py"] = ast.parse(other)
        mod, src = ("other.py", other)
    (line,) = _plant_line(src)
    problems, _reads = _constant_problems(trees, "main.py", "BAN_RECORD_STATUSES")
    assert (word, mod, line) in {(w, m, ln) for w, m, ln, _t in problems}, (control, word, mod, line, problems)


def test_control_the_products_read_shape_is_a_clean_constant():
    """The clean control: the product's own read shape gives no problem and
    is examined as one read in its function."""
    problems, reads = _constant_problems({"main.py": ast.parse(PLANTED_CONST)}, "main.py", "BAN_RECORD_STATUSES")
    assert problems == [], problems
    assert [(m, f, s) for m, f, _l, s in reads] == [("main.py", "_live", "N[e].items()")], reads


# -- F3 (fix 1): the due reasons and their order -------------------------------

def test_ban_ended_is_the_last_due_reason_and_answers_alone_only():
    """_pc_snapshot_due, on the scripted session the Player Cards tests use:
    'ban_ended' is due exactly when the ban read says so and nothing earlier
    in the order holds; when another reason holds, that one is the reason."""
    from datetime import timedelta
    from test_player_cards_server import Scripted, _due_row, _run
    today = datetime(2026, 11, 14, 0, 5, tzinfo=timezone.utc)
    later, before = today + timedelta(seconds=30), today - timedelta(days=1)

    def due(row, ended):
        db = Scripted({"SELECT (SELECT MAX(taken_at)": [row], "AS ban_ended": [[{"ban_ended": ended}]]})
        return _run(main._pc_snapshot_due(db)), db.count("AS ban_ended")

    old = int(main._PC_POOL_RULE) - 1
    assert due(_due_row(later, today + timedelta(hours=5), today), True) == ("ban_ended", 1)
    assert due(_due_row(later, today + timedelta(hours=5), today), False) == (None, 1)
    # an earlier reason holds: it is the reason, and the ban read is not made
    assert due(_due_row(before, today + timedelta(minutes=1), today), True) == ("daily", 0)
    assert due(_due_row(later, today + timedelta(hours=5), today, last_rule=old), True) == ("rule", 0)
    assert due(_due_row(None, today, today, last_rule=old), True) == ("first", 0)
    read = " ".join(__import__("inspect").getsource(main._pc_snapshot_due).split())
    assert read.index('return "first"') < read.index('return "rule"') < read.index('return "daily"') \
        < read.index('return "ban_ended" if ended else None')
    assert "async with db.begin_nested():" in read and "return None" in read
