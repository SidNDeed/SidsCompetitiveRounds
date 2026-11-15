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
    assert main.BAN_DURATION_MAX_MINUTES == 10 * 365 * 24 * 60
    for ok in (1, 60, main.BAN_DURATION_MAX_MINUTES):
        assert _req(duration_minutes=ok).duration_minutes == ok
    # the 1.41.0 request carries no field: permanent, and not a length change
    old = _req()
    assert old.duration_minutes is None and "duration_minutes" not in old.model_fields_set
    # an explicit null is SENT: it makes an active ban permanent
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


def _end_line():
    ns = {"datetime": datetime}
    exec(compile(ast.Module(body=[_bot_function("_ban_end_line")], type_ignores=[]), BOT, "exec"), ns)
    return ns["_ban_end_line"]


def test_the_bot_end_line_reads_the_end_or_permanent_and_never_raises():
    line = _end_line()
    end = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert line({"expires_at": "2031-01-02T03:04:05Z"}) == "Ends: <t:%d:F>" % int(end.timestamp())
    assert line({"expires_at": None}) == "Ends: **Permanent**"
    # an api older than the key: no line, the post is the one it was before
    assert line({"id": "x"}) == ""
    for odd in ({"expires_at": "not a time"}, {"expires_at": 12}, None, "row"):
        assert line(odd) == ""


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
    found = _module_ban_state(_module_trees())
    assert found == set(BAN_STATE_ALLOWED), (sorted(found), sorted(BAN_STATE_ALLOWED))


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

