"""A series or game a moderator voided stays out of every streak a player is
shown (owner ruling, 16 Nov 2026). One definition: every SQL statement under
backend/api that orders series or matches for a streak walk names the
invalidated filter, in the house form `<alias>.invalidated_at IS NULL`; the
Discord bot walks nothing and shows the server's fields.

THE UNIVERSE is derived from the code alone: every function (nested ones
included) of every .py file under backend/api and of backend/discord_bot.py
whose AST holds an identifier, attribute, keyword name, argument name or
string constant containing "streak". CLASSIFIED below classifies EVERY
function of the universe: WALK (it orders one of the four streak tables for
a streak) or NOT A WALK with a reason. The two sets are compared in both
directions (lessons 732, 1190):
  - a function of the universe that the table lacks is red;
  - a table row whose function is gone is red;
  - a WALK row in which the arms below find no statement is red;
  - a statement the arms find outside a WALK row is red;
  - a statement the arms find without the filter for its alias is red;
  - a bot function that reads a match list or a game's "won" is red (the
    bot's rows are all NOT A WALK, each naming the server fields it shows,
    and each named field must be a string in that function).

THE ARMS (which statements of a function are streak-walk statements). A
string literal (or the literal text of an f-string) is an ORDERING STATEMENT
when it holds ORDER BY and reads one of ranked_series, matches, team_series,
team_matches after FROM or JOIN. It is a streak-walk statement when, judged
inside the innermost function that holds it:
  (a) that function's name contains "streak"; or
  (b) it sits inside the arguments of a call whose callee name contains
      "streak"; or
  (c) it is bound by an assignment to a name, and that name, or a name later
      assigned from an expression that reads it (followed to a fixed point),
      contains "streak" or is passed to a call whose callee contains "streak".

Every red kind has a planted control below.

The /health `voided_streak_build` word follows the ban_expiry_build test's
form (test_ban_expiry_build_health_word.py).
"""
import ast
import asyncio
import os
import re

import pydantic
import pytest

import main
import schemas

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
API_DIR = os.path.join(BACKEND, "api")
BOT_FILE = "discord_bot.py"
STREAK_TABLES = ("ranked_series", "matches", "team_series", "team_matches")
_SQL_KEYWORDS = frozenset((
    "where", "join", "left", "right", "inner", "outer", "full", "cross", "on",
    "order", "group", "limit", "union", "using", "natural", "lateral", "having",
    "window", "offset", "for", "and", "or",
))
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(%s)\b(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?"
    % "|".join(STREAK_TABLES), re.IGNORECASE)
_ORDER_RE = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)

WALK = "WALK"
NOT = "NOT A WALK"

# Every function of the universe, by (file, function name). A WALK row's
# statements are checked by the arms; a NOT A WALK row says why in a few
# words; a bot row names the server fields it shows.
CLASSIFIED = {
    ("main.py", "get_ranked_streak"): (WALK, "ranked_series, newest first: achievements and /series/recent"),
    ("main.py", "get_player_stats"): (WALK, "ranked series, ranked game and casual walks"),
    ("main.py", "_h2h_modes_block"): (WALK, "the pair's ranked series for the h2h streak"),
    ("main.py", "get_player_team_stats"): (WALK, "team_series, newest first: the 2v2 streak"),
    ("main.py", "_walk_streak"): (NOT, "folds rows get_player_stats selected"),
    ("main.py", "_h2h_series_streak_and_net"): (NOT, "folds rows _h2h_modes_block selected"),
    ("main.py", "health_check"): (NOT, "passes build-marker constants"),
    ("main.py", "submit_match"): (NOT, "writes stored counters; calls get_ranked_streak"),
    ("main.py", "get_recent_series"): (NOT, "passes get_ranked_streak's value through"),
    ("main.py", "get_recent_multimode_series"): (NOT, "docstring mention only"),
    ("main.py", "get_player_rating_history"): (NOT, "docstring mention only"),
    ("title_ladders.py", "record_completed_games"): (NOT, "writes the stored Apex run counter"),
    ("title_ladders.py", "get_title_ladders"): (NOT, "reads the stored Apex run counter"),
    ("title_ladders.py", "counted_delta"): (NOT, "docstring mention only"),
    ("title_ladders.py", "record_late_play_gold"): (NOT, "a gold source label"),
    (BOT_FILE, "streak_str"): (NOT, "a label for a signed number", ()),
    (BOT_FILE, "_streak_field"): (NOT, "reads the server field its caller names", ()),
    (BOT_FILE, "cmd_rank"): (NOT, "shows server fields",
                             ("best_ranked_streak", "current_ranked_game_streak")),
    (BOT_FILE, "cmd_stats"): (NOT, "shows a server field", ("best_casual_streak",)),
    (BOT_FILE, "cmd_mystats"): (NOT, "shows server fields",
                                ("current_ranked_game_streak", "current_casual_streak",
                                 "best_ranked_streak", "best_casual_streak", "current_streak")),
    (BOT_FILE, "log_series_result"): (NOT, "shows server fields", ("p1_streak", "p2_streak")),
}


# -- the arms ---------------------------------------------------------------

def _literal_text(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}"
                       for v in node.values)
    return None


def _callee(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _streak_tables(sql):
    """[(table, alias)] for every streak table the statement reads."""
    out = []
    for m in _TABLE_RE.finditer(sql):
        alias = m.group(2)
        if alias is None or alias.lower() in _SQL_KEYWORDS:
            alias = m.group(1)
        out.append((m.group(1), alias))
    return out


def unfiltered_tables(sql):
    """The (table, alias) pairs of `sql` without `<alias>.invalidated_at IS NULL`."""
    return [(t, a) for t, a in _streak_tables(sql)
            if not re.search(r"\b%s\.invalidated_at\s+IS\s+NULL\b" % re.escape(a),
                             sql, re.IGNORECASE)]


def _is_ordering_statement(sql):
    return bool(_ORDER_RE.search(sql)) and bool(_streak_tables(sql))


class _Scope:
    """One function body (nested function bodies excluded), with parents."""

    def __init__(self, name, body):
        self.name = name
        self.parent = {}
        self.nodes = []
        stack = [(stmt, None) for stmt in body]
        while stack:
            node, par = stack.pop()
            self.parent[node] = par
            self.nodes.append(node)
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.Lambda, ast.ClassDef)):
                    continue
                stack.append((child, node))

    def ancestors(self, node):
        node = self.parent.get(node)
        while node is not None:
            yield node
            node = self.parent.get(node)


def _scopes(tree):
    yield _Scope(None, [n for n in tree.body
                        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                              ast.ClassDef))])
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield _Scope(node.name, node.body)


def _targets(assign):
    targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
    return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}


def _reads(node):
    return {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def streak_walk_statements(tree, filename="<src>"):
    """[(filename, line, function, sql)] for every streak-walk statement."""
    found = []
    for scope in _scopes(tree):
        assigns = [n for n in scope.nodes if isinstance(n, (ast.Assign, ast.AnnAssign))
                   and getattr(n, "value", None) is not None]
        passed = set()
        for call in (n for n in scope.nodes if isinstance(n, ast.Call)
                     and "streak" in _callee(n).lower()):
            for arg in list(call.args) + [k.value for k in call.keywords]:
                passed |= _reads(arg)
        for node in scope.nodes:
            sql = _literal_text(node)
            if sql is None or not _is_ordering_statement(sql):
                continue
            if isinstance(scope.parent.get(node), ast.JoinedStr):
                continue  # a piece of an f-string; the JoinedStr itself is judged
            walk = scope.name is not None and "streak" in scope.name.lower()
            ancestors = list(scope.ancestors(node))
            if any(isinstance(a, ast.Call) and "streak" in _callee(a).lower()
                   for a in ancestors):
                walk = True
            bound = next((a for a in ancestors
                          if isinstance(a, (ast.Assign, ast.AnnAssign))), None)
            if not walk and bound is not None:
                names = _targets(bound)
                grew = True
                while grew:
                    grew = False
                    for a in assigns:
                        if (a is not bound and _reads(a.value) & names
                                and not _targets(a) <= names):
                            names |= _targets(a)
                            grew = True
                walk = any("streak" in n.lower() for n in names) or bool(names & passed)
            if walk:
                found.append((filename, node.lineno, scope.name, sql))
    return found


# -- the universe and the two-way comparison --------------------------------

def _mentions_streak(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Name):
            s = n.id
        elif isinstance(n, ast.Attribute):
            s = n.attr
        elif isinstance(n, ast.keyword):
            s = n.arg
        elif isinstance(n, ast.arg):
            s = n.arg
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s = n.name
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            s = n.value
        else:
            continue
        if s and "streak" in s.lower():
            return True
    return False


def universe(trees):
    """{(file, function name): node} for every function mentioning "streak"."""
    out, dup = {}, []
    for filename, tree in trees.items():
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _mentions_streak(n):
                key = (filename, n.name)
                if key in out:
                    dup.append(key)
                out[key] = n
    assert not dup, ("two functions of one name: the table cannot tell them apart", dup)
    return out


def _strings(fn):
    return {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
            and isinstance(n.value, str)}


def _bot_walks(fn):
    """A bot function that reads a match list or a game's result walks."""
    return any("/matches" in s or s == "won" for s in _strings(fn))


def census_findings(trees, table, bot_file=BOT_FILE):
    """Every red finding of the census, as (kind, file, function, detail)."""
    uni = universe(trees)
    stmts = [s for f, t in trees.items() for s in streak_walk_statements(t, f)]
    found = []
    for key in sorted(set(uni) - set(table)):
        found.append(("unclassified", key[0], key[1], uni[key].lineno))
    for key in sorted(set(table) - set(uni)):
        found.append(("row_without_function", key[0], key[1], table[key][1]))
    walk_keys = {k for k, row in table.items() if row[0] == WALK}
    with_stmt = {(f, fn) for f, _line, fn, _sql in stmts}
    for key in sorted(walk_keys - with_stmt):
        found.append(("walk_row_without_statement", key[0], key[1], table[key][1]))
    for f, line, fn, sql in stmts:
        if (f, fn) not in walk_keys:
            found.append(("statement_outside_walk_row", f, fn, line))
        missing = unfiltered_tables(sql)
        if missing:
            found.append(("unfiltered", f, fn, (line, missing)))
    for key in sorted(k for k in uni if k[0] == bot_file):
        row = table.get(key)
        if row is None:
            continue
        if row[0] != NOT or _bot_walks(uni[key]):
            found.append(("bot_walks", key[0], key[1], uni[key].lineno))
        for field in (row[2] if len(row) > 2 else ()):
            if field not in _strings(uni[key]):
                found.append(("bot_field_not_read", key[0], key[1], field))
    return found


def _live_trees():
    trees = {}
    for name in sorted(os.listdir(API_DIR)):
        if name.endswith(".py"):
            with open(os.path.join(API_DIR, name), encoding="utf-8") as fh:
                trees[name] = ast.parse(fh.read())
    with open(os.path.join(BACKEND, BOT_FILE), encoding="utf-8") as fh:
        trees[BOT_FILE] = ast.parse(fh.read())
    return trees


def test_the_census_is_clean_in_both_directions():
    trees = _live_trees()
    assert census_findings(trees, CLASSIFIED) == []
    # The universe is derived, not listed: it must hold every row here, and
    # every WALK row must carry a filtered statement (checked above).
    assert len(universe(trees)) == len(CLASSIFIED)


# -- controls: one planted source per red kind ------------------------------

_P_FN_NAME = '''
async def get_some_streak(db, pid):
    rows = await db.execute(text("""
        SELECT rs.winner_id FROM ranked_series rs
        WHERE rs.status = 'completed' AND (rs.player1_id = :pid OR rs.player2_id = :pid)
        ORDER BY rs.completed_at DESC
    """), {"pid": pid})
    return rows
'''

_P_CALL_ARG = '''
async def stats(db, pid):
    best = _walk_streak((await db.execute(text("""
        SELECT m.winner_id FROM matches m
        WHERE (m.player1_id = :pid OR m.player2_id = :pid)
        ORDER BY m.ended_at ASC
    """), {"pid": pid})).all(), pid)
    return best
'''

_P_FLOW = '''
async def stats(db, pid):
    q = await db.execute(text("""
        SELECT s.winner_team FROM team_series s
        WHERE s.status = 'completed'
        ORDER BY s.completed_at DESC
    """), {"pid": pid})
    rows = q.mappings().all()
    return fold_the_streak(rows)
'''

_P_NAME = '''
async def stats(db, pid):
    my_streak_rows = await db.execute(text(f"""
        SELECT tm.winner_team FROM team_matches AS tm
        WHERE {pid} IS NOT NULL
        ORDER BY tm.ended_at DESC
    """))
    return my_streak_rows
'''

ARMS = [
    (_P_FN_NAME, "get_some_streak", ("ranked_series", "rs")),
    (_P_CALL_ARG, "stats", ("matches", "m")),
    (_P_FLOW, "stats", ("team_series", "s")),
    (_P_NAME, "stats", ("team_matches", "tm")),
]
ARM_IDS = ["function_name", "call_argument", "flow_to_streak_call", "bound_name"]


def _planted(src, table, name="planted.py"):
    return census_findings({name: ast.parse(src)}, table)


@pytest.mark.parametrize("src, fn, table", ARMS, ids=ARM_IDS)
def test_an_arm_finds_a_planted_walk_and_refuses_it_without_the_filter(src, fn, table):
    got = _planted(src, {("planted.py", fn): (WALK, "planted")})
    assert [(k, f, n) for k, f, n, _ in got] == [("unfiltered", "planted.py", fn)], got
    assert got[0][3][1] == [table], got


@pytest.mark.parametrize("src, fn, table", ARMS, ids=ARM_IDS)
def test_the_same_walk_with_the_filter_is_clean(src, fn, table):
    fixed = src.replace("ORDER BY", "AND %s.invalidated_at IS NULL\n        ORDER BY" % table[1], 1)
    assert _planted(fixed, {("planted.py", fn): (WALK, "planted")}) == []


def test_red_a_function_of_the_universe_that_the_table_lacks():
    """A walk in a function not called "streak", its rows walked inline:
    it mentions a streak, so it is in the universe and must be classified."""
    src = '''
async def profile_line(db, pid):
    rows = (await db.execute(text("SELECT m.winner_id FROM matches m ORDER BY m.ended_at DESC"))).all()
    run = 0
    for r in rows:
        if r[0] != pid:
            break
        run += 1
    return {"streak": run}
'''
    got = _planted(src, {})
    assert [(k, n) for k, _f, n, _ in got] == [("unclassified", "profile_line")], got


def test_red_a_table_row_whose_function_is_gone():
    got = _planted("def unrelated():\n    return 1\n",
                   {("planted.py", "get_old_streak"): (NOT, "gone")})
    assert [(k, n) for k, _f, n, _ in got] == [("row_without_function", "get_old_streak")], got


def test_red_a_walk_row_in_which_the_arms_find_no_statement():
    """The inline walk above, classified WALK: its statement is bound to
    `rows`, which no arm reaches, so the WALK row has no checked statement."""
    src = '''
async def profile_line(db, pid):
    rows = (await db.execute(text("SELECT m.winner_id FROM matches m ORDER BY m.ended_at DESC"))).all()
    return {"streak": len(rows)}
'''
    got = _planted(src, {("planted.py", "profile_line"): (WALK, "planted")})
    assert [(k, n) for k, _f, n, _ in got] == [("walk_row_without_statement", "profile_line")], got


def test_red_a_statement_the_arms_find_outside_a_walk_row():
    fixed = _P_FN_NAME.replace("ORDER BY", "AND rs.invalidated_at IS NULL\n        ORDER BY", 1)
    got = _planted(fixed, {("planted.py", "get_some_streak"): (NOT, "planted")})
    assert [(k, n) for k, _f, n, _ in got] == [("statement_outside_walk_row", "get_some_streak")], got


def test_red_a_bot_function_that_walks_a_matches_list():
    """The bot's walk this lane removed, planted back: it reads the match
    list and each game's "won", so it is red whatever its row says."""
    src = '''
async def current_streak(steam_id):
    hist = await api_get(f"/players/{steam_id}/matches?limit=50")
    first = bool(hist[0].get("won"))
    return sum(1 for m in hist if bool(m.get("won")) == first)
'''
    table = {(BOT_FILE, "current_streak"): (NOT, "planted", ())}
    got = census_findings({BOT_FILE: ast.parse(src)}, table)
    assert [(k, n) for k, _f, n, _ in got] == [("bot_walks", "current_streak")], got


def test_red_a_bot_row_naming_a_field_its_function_does_not_read():
    src = '''
async def cmd_x(ctx):
    s = await api_get("/players/1")
    return streak_str(s.get("current_casual_streak", 0))
'''
    table = {(BOT_FILE, "cmd_x"): (NOT, "planted", ("current_ranked_game_streak",))}
    got = census_findings({BOT_FILE: ast.parse(src)}, table)
    assert [(k, n, d) for k, _f, n, d in got] == [
        ("bot_field_not_read", "cmd_x", "current_ranked_game_streak")], got


def test_an_ordering_statement_that_feeds_no_streak_is_not_a_walk():
    """The match history orders matches and keeps voided rows on purpose (its
    answer is frozen for the released client); it is not a streak walk."""
    src = '''
async def history(db, pid):
    rows = await db.execute(text("""
        SELECT m.id FROM matches m WHERE m.player1_id = :pid ORDER BY m.ended_at DESC
    """), {"pid": pid})
    return rows
'''
    assert streak_walk_statements(ast.parse(src)) == []


def test_a_filter_on_another_alias_does_not_count():
    sql = ("SELECT rs.winner_id FROM ranked_series rs JOIN matches m ON m.series_id = rs.id "
           "WHERE m.invalidated_at IS NULL ORDER BY rs.completed_at")
    assert unfiltered_tables(sql) == [("ranked_series", "rs")]


# -- /health voided_streak_build ---------------------------------------------

KEY = "voided_streak_build"
CONST = "_VOIDED_STREAK_BUILD"


class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("voided_streak_build: the database is down")

    async def rollback(self):
        pass


def _main_tree():
    with open(main.__file__, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def test_both_health_arms_carry_the_build_marker():
    """Both arms pass the constant and nothing else in main.py passes the
    key; the constant is bound once, to 1 (the train refuses a falsy word)."""
    tree = _main_tree()
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == KEY]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == KEY]
    assert (connected, degraded) == ([CONST], [CONST])
    everywhere = [k for k in ast.walk(tree)
                  if isinstance(k, ast.keyword) and k.arg == KEY]
    assert len(everywhere) == 2, len(everywhere)
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == CONST and isinstance(n.ctx, ast.Store)]
    (binding,) = [n for n in tree.body if isinstance(n, ast.Assign)
                  and [ast.unparse(t) for t in n.targets] == [CONST]]
    assert len(stores) == 1 and ast.unparse(binding.value) == "1", ast.unparse(binding)


def test_the_health_schema_requires_the_word_and_the_answer_carries_it():
    field = schemas.HealthResponse.model_fields.get(KEY)
    assert field is not None and field.annotation is int and field.is_required(), field
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and answer[KEY] == 1, answer
    answer.pop(KEY)
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)
