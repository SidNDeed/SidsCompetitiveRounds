"""R1 (B4): ONE definition of an active ban, and every reader uses it.

A ban is active while its row is not lifted and its end, if it has one, is
ahead of the database's clock: models.player_ban_active_sql(alias). This test
derives the readers instead of keeping a list of call sites (learning 1035):
it walks the AST of every module under backend/api and of
backend/discord_bot.py and collects

  - every string literal that names the table player_bans (docstrings and
    other bare string statements are not code and are skipped), and
  - every ORM use of the PlayerBan model (imports and the class itself are
    skipped).

Each literal is judged inside its ROOT expression, the expression that ends
where the SQL stops being built: climbing from the literal through string
concatenation (BinOp), f-strings (JoinedStr / FormattedValue) and calls
(text(...), db.execute(...)). Every `player_bans <alias>` the root's SQL text
names (the alias is the table name itself when none follows) must be covered
by a `player_ban_active_sql("<alias>")` call in the same root. A site that
does not compare a ban's state at all (a writer, a lookup by id, a count of
an admin's bans by time) is on ALLOWED, keyed by module and function, with
the number of roots it holds and the reason. The counts are exact both ways:
a new uncovered reader in an allowed function fails, and so does an allowed
entry whose reader is gone.

The negative control plants an uncovered reader and requires the walk to
report it; the positive control plants a covered one and requires silence.
"""
import ast
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
API = os.path.join(BACKEND, "api")
BOT = os.path.join(BACKEND, "discord_bot.py")

DEFINITION = "player_ban_active_sql"
TABLE = re.compile(r"\bplayer_bans\b")
# `player_bans` followed by an alias, or by a keyword (then the table name is
# its own alias). AS is optional in SQL.
ALIAS = re.compile(r"\bplayer_bans\b(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?", re.I)
KEYWORDS = {
    "where", "set", "on", "join", "left", "right", "inner", "outer", "cross", "order",
    "group", "limit", "using", "and", "or", "for", "returning", "values", "select",
    "union", "having", "offset", "natural", "full", "window", "except", "intersect",
}
CLIMB = (ast.BinOp, ast.JoinedStr, ast.FormattedValue, ast.Call)

# (module, qualname) -> (roots, reason). Each is a site whose SQL names
# player_bans but does not decide whether an account is under an active ban.
ALLOWED = {
    ("main.py", "_ban_rate_gate_or_raise"): (
        1, "counts the ADMIN's bans written in the last five minutes (velocity), by banned_at"),
    ("main.py", "get_recent_bans"): (
        1, "the cutoff lookup reads one row's banned_at BY ID (the bot's cursor), whatever its state"),
    ("main.py", "_apply_ban_core"): (
        1, "the writer's close of an ENDED open row (expires_at <= NOW()): the complement of the definition, under the identity lock"),
    ("models.py", "PlayerBan"): (
        1, "__tablename__ of the model itself"),
}
# ORM uses of the PlayerBan model: (module, qualname) -> (uses, reason).
ALLOWED_ORM = {
    ("main.py", "_apply_ban_core"): (
        1, "the ORM insert of a new ban row (the writer)"),
}


def _parents(tree):
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _qualname(node, parents):
    names = []
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return ".".join(reversed(names)) or "<module>"


def _root(node, parents):
    while node in parents and isinstance(parents[node], CLIMB):
        node = parents[node]
    return node


def _bare_string(node, parents):
    """A string statement on its own line (a docstring or a stray literal)."""
    p = parents.get(node)
    return isinstance(p, ast.Expr) and p.value is node


def _covered(root):
    return {n.args[0].value for n in ast.walk(root)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == DEFINITION
            and len(n.args) == 1 and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)}


def _sql_text(root):
    """The root's SQL: its string literals in source order, leaving out the
    definition's own alias argument and the bind parameters (dict keys and
    values, keyword arguments), which are not SQL."""
    parts = []

    def visit(node, skip):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not skip:
                parts.append(node)
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == DEFINITION:
            return
        for child in ast.iter_child_nodes(node):
            visit(child, skip or isinstance(node, (ast.Dict, ast.keyword)))
    visit(root, False)
    parts.sort(key=lambda n: (n.lineno, n.col_offset))
    return " ".join(n.value for n in parts)


def _aliases(sql):
    out = set()
    for m in ALIAS.finditer(sql):
        word = m.group(1)
        out.add("player_bans" if word is None or word.lower() in KEYWORDS else word)
    return out


def scan_source(module, src):
    """(readers, orm): readers maps (module, qualname) to a list of
    (lineno, uncovered aliases) per root; orm maps (module, qualname) to the
    line numbers of PlayerBan uses."""
    tree = ast.parse(src)
    parents = _parents(tree)
    readers, roots_seen, orm = {}, set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and TABLE.search(node.value):
            if _bare_string(node, parents):
                continue
            root = _root(node, parents)
            if id(root) in roots_seen:
                continue
            roots_seen.add(id(root))
            missing = sorted(_aliases(_sql_text(root)) - _covered(root))
            readers.setdefault((module, _qualname(node, parents)), []).append((root.lineno, missing))
        elif isinstance(node, ast.Name) and node.id == "PlayerBan" and isinstance(node.ctx, ast.Load):
            orm.setdefault((module, _qualname(node, parents)), []).append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "PlayerBan":
            orm.setdefault((module, _qualname(node, parents)), []).append(node.lineno)
    return readers, orm


def _modules():
    out = []
    for name in sorted(os.listdir(API)):
        if name.endswith(".py"):
            out.append((name, os.path.join(API, name)))
    out.append(("discord_bot.py", BOT))
    return out


def scan_tree():
    readers, orm = {}, {}
    for name, path in _modules():
        with open(path, encoding="utf-8") as fh:
            r, o = scan_source(name, fh.read())
        readers.update(r)
        orm.update(o)
    return readers, orm


def judge(readers, orm, whole_tree=True):
    """Every problem with the derived readers, and the counts. On the whole
    tree an allowed site that is gone is a problem too; a planted source
    holds only the planted function, so that check is for the tree alone."""
    problems = []
    counts = {"roots": 0, "covered": 0, "allowed": 0, "orm": 0}
    for key, roots in sorted(readers.items()):
        counts["roots"] += len(roots)
        if key in ALLOWED:
            want = ALLOWED[key][0]
            uncovered = [r for r in roots if r[1]]
            if len(uncovered) != want:
                problems.append(("allowed count moved", key, want, uncovered))
            counts["allowed"] += len(uncovered)
            counts["covered"] += len(roots) - len(uncovered)
            continue
        for lineno, missing in roots:
            if missing:
                problems.append(("reader without the definition", key, lineno, missing))
            else:
                counts["covered"] += 1
    for key in (ALLOWED if whole_tree else ()):
        if key not in readers:
            problems.append(("allowed site gone", key))
    for key, lines in sorted(orm.items()):
        counts["orm"] += len(lines)
        want = ALLOWED_ORM.get(key, (0, ""))[0]
        if len(lines) != want:
            problems.append(("PlayerBan use outside ALLOWED_ORM", key, lines))
    for key in (ALLOWED_ORM if whole_tree else ()):
        if key not in orm:
            problems.append(("allowed ORM site gone", key))
    return problems, counts


def test_every_reader_of_player_bans_uses_the_one_definition(capsys):
    readers, orm = scan_tree()
    problems, counts = judge(readers, orm)
    with capsys.disabled():
        print("\n[ban-definition] roots %(roots)d covered %(covered)d allowed %(allowed)d "
              "orm %(orm)d" % counts)
    assert not problems, problems
    # the walk reached the readers this lane changed (no silent empty scan)
    assert counts["covered"] >= 25 and counts["orm"] == 1, counts
    assert ("tournaments.py", "_player_id_banned") in readers
    assert ("main.py", "_is_banned") in readers


def test_the_definition_compares_the_end_on_the_database_clock():
    import models
    assert models.player_ban_active_sql("pb") == (
        "(pb.unbanned_at IS NULL AND (pb.expires_at IS NULL OR pb.expires_at > NOW()))")
    for bad in ("", "1x", "pb;", "pb.x", "PB"):
        with pytest.raises(ValueError):
            models.player_ban_active_sql(bad)


PLANTED_UNCOVERED = '''
async def planted(db):
    return await db.execute(text(
        "SELECT 1 FROM player_bans pb WHERE pb.steam_id = :s AND pb.unbanned_at IS NULL"), {"s": "1"})
'''
PLANTED_COVERED = '''
async def planted(db):
    return await db.execute(text(
        "SELECT 1 FROM player_bans pb WHERE pb.steam_id = :s AND " + player_ban_active_sql("pb")), {"s": "1"})
'''
PLANTED_BARE = '''
async def planted(db):
    return await db.execute(text(
        "SELECT reason FROM player_bans WHERE steam_id = :s AND unbanned_at IS NULL"), {"s": "1"})
'''
PLANTED_ORM = '''
async def planted(db):
    return await db.execute(select(PlayerBan).where(PlayerBan.unbanned_at.is_(None)))
'''


def test_negative_control_a_planted_reader_is_reported():
    for src, alias in ((PLANTED_UNCOVERED, "pb"), (PLANTED_BARE, "player_bans")):
        readers, orm = scan_source("planted.py", src)
        problems, _ = judge(readers, orm, whole_tree=False)
        assert problems == [("reader without the definition", ("planted.py", "planted"), 3, [alias])], problems
    readers, orm = scan_source("planted.py", PLANTED_ORM)
    problems, _ = judge(readers, orm, whole_tree=False)
    assert problems == [("PlayerBan use outside ALLOWED_ORM", ("planted.py", "planted"), [3, 3])], problems


def test_positive_control_a_covered_reader_is_silent():
    readers, orm = scan_source("planted.py", PLANTED_COVERED)
    assert judge(readers, orm, whole_tree=False) == ([], {"roots": 1, "covered": 1, "allowed": 0, "orm": 0})


def test_an_allowed_function_gaining_a_reader_is_reported():
    """A second uncovered root inside an allowed function moves its count."""
    src = '''
async def _ban_rate_gate_or_raise(db):
    await db.execute(text("SELECT COUNT(*) FROM player_bans WHERE banned_by_steam_id = :a"))
    await db.execute(text("SELECT 1 FROM player_bans WHERE steam_id = :s AND unbanned_at IS NULL"))
'''
    readers, orm = scan_source("main.py", src)
    problems, _ = judge(readers, orm, whole_tree=False)
    assert ("allowed count moved", ("main.py", "_ban_rate_gate_or_raise"), 1) == problems[0][:3], problems
