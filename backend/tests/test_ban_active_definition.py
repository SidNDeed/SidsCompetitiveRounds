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
(text(...), db.execute(...)). The root's SQL text is rebuilt in source order
with a marker where each `player_ban_active_sql("<alias>")` call stands.

Coverage is judged per TABLE OCCURRENCE, not per root (fix 1, F4): every
`player_bans <alias>` (the alias is the table name itself when none follows)
is one reader whose scope is the innermost parenthesised group holding it
(the whole statement at the top level). A marker for an alias belongs to the
innermost scope of an occurrence of that alias that holds the marker; each
scope needs as many markers of an alias as it holds occurrences of it. So
two subqueries that share an alias cannot cover each other, and neither can
an outer reader be covered by a marker inside a nested one.

A site that does not compare a ban's state at all (a writer, a lookup by id,
a count of an admin's bans by time) is on ALLOWED, keyed by module and
function, with the number of roots it holds and the reason. The counts are
exact both ways: a new uncovered reader in an allowed function fails, and so
does an allowed entry whose reader is gone. Two ORM forms the walk does not
model (`aliased(PlayerBan)` and a relationship to PlayerBan) fail it outright
wherever they appear; none exists.

The negative controls plant uncovered readers (one per shape the walk must
see) and require the walk to report each; the positive control plants a
covered one and requires silence.
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
# A qualified column (`player_bans.steam_id`) is not a table occurrence.
ALIAS = re.compile(r"\bplayer_bans\b(?!\s*\.)(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?", re.I)
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
        2, "the writer's close of an ENDED open row (expires_at <= NOW()): the complement of the definition,"
           " under the identity lock; and the INSERT of the new ban row (the cap ruling: start and end from one"
           " clock read), which reads no row"),
    ("models.py", "PlayerBan"): (
        1, "__tablename__ of the model itself"),
    # BAN-RECORD-1 (migration 429): the ban record's two writers.
    ("main.py", "admin_ban_details"): (
        2, "the details route reads ONE ban row BY ID after the definition chose it (_active_ban_details, under"
           " the identity lock), and writes that row's texts by id"),
    # BAN-RECORD-1 FIX N1 (RULING-BAN-RECORD-R1): 2 -> 1. The second statement, which cleared the texts of
    # the ban_details records, went with N1: a ban_details record holds the ban's id and the word of each
    # change, never a text.
    ("main.py", "_ban_record_forget"): (
        1, "the account deletion clears the kept name and the details of EVERY ban row of the account,"
           " whatever each ban's state"),
}
# ORM uses of the PlayerBan model: (module, qualname) -> (uses, reason). None
# since the cap ruling: the writer inserts by SQL (main._apply_ban_core).
ALLOWED_ORM = {}


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


# A marker is MARK + the alias in hex + MARK: no SQL text holds a NUL, and the
# hex keeps a marker for the bare table from reading as an occurrence of it.
MARK = "\x00"


def _definition_alias(node):
    """The alias of a call to the definition whose arguments are positional
    str literals only, else None. The second argument, when present, is the
    instant form (`at`, a timestamptz bind cast): the same definition read at
    that instant, so it covers its alias exactly as the plain form does --
    it is the one helper, not a second spelling (fix 1, F3 R-f)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == DEFINITION \
            and 1 <= len(node.args) <= 2 and not node.keywords \
            and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args):
        return node.args[0].value
    return None


def _sql_text(root):
    """The root's SQL in source order (an in-order walk: BinOp left then
    right, JoinedStr values, call arguments), with a marker where each call
    to the definition stands, leaving out the bind parameters (dict keys and
    values, keyword arguments), which are not SQL."""
    parts = []

    def visit(node, skip):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not skip:
                parts.append(node.value)
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == DEFINITION:
            alias = _definition_alias(node)
            if alias is not None and not skip:
                parts.append(" " + MARK + alias.encode().hex() + MARK + " ")
            return
        for child in ast.iter_child_nodes(node):
            visit(child, skip or isinstance(node, (ast.Dict, ast.keyword)))
    visit(root, False)
    return " ".join(parts)


def _groups(sql):
    """(start, end) of every parenthesised group, quotes respected."""
    out, stack, quoted = [], [], False
    for i, ch in enumerate(sql):
        if ch == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif ch == "(":
            stack.append(i)
        elif ch == ")" and stack:
            out.append((stack.pop(), i))
    return out


def _scope(pos, groups, length):
    inner = (-1, length)
    for a, b in groups:
        if a < pos < b and (b - a) < (inner[1] - inner[0]):
            inner = (a, b)
    return inner


def occurrences(sql):
    """[(position, alias)] of every `player_bans` reader in the text."""
    out = []
    for m in ALIAS.finditer(sql):
        word = m.group(1)
        out.append((m.start(), "player_bans" if word is None or word.lower() in KEYWORDS else word))
    return out


def uncovered(sql):
    """The aliases of the occurrences no marker of their scope covers."""
    groups = _groups(sql)
    occ = [(alias, _scope(pos, groups, len(sql))) for pos, alias in occurrences(sql)]
    need = {}
    for alias, scope in occ:
        need[(alias, scope)] = need.get((alias, scope), 0) + 1
    have = {}
    for m in re.finditer(re.escape(MARK) + r"([^" + MARK + r"]*)" + re.escape(MARK), sql):
        alias = bytes.fromhex(m.group(1)).decode()
        holders = [scope for (a, scope) in need if a == alias and scope[0] < m.start() < scope[1]]
        if holders:
            best = min(holders, key=lambda s: s[1] - s[0])
            have[(alias, best)] = have.get((alias, best), 0) + 1
    missing = []
    for key, n in need.items():
        missing.extend([key[0]] * max(0, n - have.get(key, 0)))
    return sorted(missing)


def _tripwire(node):
    """An ORM form of PlayerBan the walk does not model, else None."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
    if name not in ("aliased", "relationship", "backref"):
        return None
    for a in list(node.args) + [k.value for k in node.keywords]:
        if (isinstance(a, ast.Name) and a.id == "PlayerBan") or \
                (isinstance(a, ast.Constant) and a.value == "PlayerBan"):
            return name
    return None


def scan_source(module, src):
    """(readers, orm): readers maps (module, qualname) to a list of
    (lineno, uncovered aliases, occurrences) per root; orm maps (module,
    qualname) to the line numbers of PlayerBan uses, and an unmodelled ORM
    form is entered under ("<tripwire>", form) with its line."""
    tree = ast.parse(src)
    parents = _parents(tree)
    readers, roots_seen, orm = {}, set(), {}
    for node in ast.walk(tree):
        trip = _tripwire(node)
        if trip:
            orm.setdefault(("<tripwire>", "%s(PlayerBan) in %s" % (trip, module)), []).append(node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and TABLE.search(node.value):
            if _bare_string(node, parents):
                continue
            root = _root(node, parents)
            if id(root) in roots_seen:
                continue
            roots_seen.add(id(root))
            sql = _sql_text(root)
            readers.setdefault((module, _qualname(node, parents)), []).append(
                (root.lineno, uncovered(sql), len(occurrences(sql))))
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
    counts = {"roots": 0, "occurrences": 0, "covered": 0, "allowed": 0, "orm": 0}
    for key, roots in sorted(readers.items()):
        counts["roots"] += len(roots)
        counts["occurrences"] += sum(r[2] for r in roots)
        if key in ALLOWED:
            want = ALLOWED[key][0]
            bad = [r[:2] for r in roots if r[1]]
            if len(bad) != want:
                problems.append(("allowed count moved", key, want, bad))
            counts["allowed"] += len(bad)
            counts["covered"] += len(roots) - len(bad)
            continue
        for lineno, missing, _n in roots:
            if missing:
                problems.append(("reader without the definition", key, lineno, missing))
            else:
                counts["covered"] += 1
    for key in (ALLOWED if whole_tree else ()):
        if key not in readers:
            problems.append(("allowed site gone", key))
    for key, lines in sorted(orm.items()):
        if key[0] == "<tripwire>":
            problems.append(("ORM form this walk does not model; extend the walk first", key[1], lines))
            continue
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
        print("\n[ban-definition] roots %(roots)d occurrences %(occurrences)d covered %(covered)d "
              "allowed %(allowed)d orm %(orm)d" % counts)
    assert not problems, problems
    # the walk reached the readers this lane changed (no silent empty scan)
    assert counts["covered"] >= 25 and counts["orm"] == 0, counts
    assert ("main.py", "_apply_ban_core") in readers and ("main.py", "_ban_set_length_core") in readers
    assert ("tournaments.py", "_player_id_banned") in readers
    assert ("main.py", "_is_banned") in readers


def test_the_definition_compares_the_end_on_the_database_clock():
    import models
    assert models.player_ban_active_sql("pb") == (
        "(pb.unbanned_at IS NULL AND (pb.expires_at IS NULL OR pb.expires_at > NOW()))")
    for bad in ("", "1x", "pb;", "pb.x", "PB"):
        with pytest.raises(ValueError):
            models.player_ban_active_sql(bad)
    # the instant form (F3): the same three facts read at a bound instant --
    # begun by then, not lifted by then, not expired by then (a ban ends at
    # the EARLIER of its lift and its expiry)
    assert models.player_ban_active_sql("b", "CAST(:t AS timestamptz)") == (
        "(b.banned_at <= CAST(:t AS timestamptz)"
        " AND (b.unbanned_at IS NULL OR b.unbanned_at > CAST(:t AS timestamptz))"
        " AND (b.expires_at IS NULL OR b.expires_at > CAST(:t AS timestamptz)))")
    for bad in ("NOW()", ":t", "CAST(:t AS date)", "CAST(:t AS timestamptz) OR TRUE", "", 5):
        with pytest.raises(ValueError):
            models.player_ban_active_sql("b", bad)


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
    assert judge(readers, orm, whole_tree=False) == (
        [], {"roots": 1, "occurrences": 1, "covered": 1, "allowed": 0, "orm": 0})


# F4: one planted reader per shape a per-root census could miss. Each must be
# reported with exactly the alias of its uncovered occurrence.
PLANTED_SHAPES = {
    "a second subquery with the same alias": ('''
async def planted(db):
    return await db.execute(text("SELECT 1 FROM t WHERE EXISTS (SELECT 1 FROM player_bans b WHERE b.unbanned_at IS NULL)"
        " OR EXISTS (SELECT 1 FROM player_bans b WHERE b.steam_id = t.s AND " + player_ban_active_sql("b") + ")"))
''', ["b"]),
    "two aliases in one statement, one bare": ('''
async def planted(db):
    return await db.execute(text("SELECT 1 FROM player_bans pb JOIN player_bans ON player_bans.steam_id = pb.steam_id"
        " WHERE " + player_ban_active_sql("pb")))
''', ["player_bans"]),
    "a reader inside a CTE": ('''
async def planted(db):
    return await db.execute(text("WITH x AS (SELECT steam_id FROM player_bans pb WHERE pb.unbanned_at IS NULL)"
        " SELECT 1 FROM player_bans pb WHERE pb.steam_id IN (SELECT steam_id FROM x) AND " + player_ban_active_sql("pb")))
''', ["pb"]),
    "an outer reader beside a covered nested one": ('''
async def planted(db):
    return await db.execute(text("SELECT 1 FROM player_bans pb WHERE pb.steam_id IN"
        " (SELECT pb.steam_id FROM player_bans pb WHERE " + player_ban_active_sql("pb") + ")"))
''', ["pb"]),
}
PLANTED_SECOND_STATEMENT = '''
async def planted(db):
    await db.execute(text("SELECT 1 FROM player_bans pb WHERE " + player_ban_active_sql("pb")))
    await db.execute(text("SELECT 1 FROM player_bans pb WHERE pb.unbanned_at IS NULL"))
'''


@pytest.mark.parametrize("shape", sorted(PLANTED_SHAPES))
def test_negative_control_each_shape_of_uncovered_occurrence_is_reported(shape):
    src, missing = PLANTED_SHAPES[shape]
    readers, orm = scan_source("planted.py", src)
    problems, counts = judge(readers, orm, whole_tree=False)
    assert problems == [("reader without the definition", ("planted.py", "planted"), 3, missing)], problems
    assert counts["occurrences"] == 2, counts


def test_negative_control_a_reader_in_a_second_statement_is_reported():
    readers, orm = scan_source("planted.py", PLANTED_SECOND_STATEMENT)
    problems, counts = judge(readers, orm, whole_tree=False)
    assert problems == [("reader without the definition", ("planted.py", "planted"), 4, ["pb"])], problems
    assert counts["roots"] == 2 and counts["covered"] == 1, counts


def test_negative_control_the_reviewers_trade_mutant_is_reported():
    """The first definition call of main._PC_TRADE_DEAD_SQL replaced by
    `b.unbanned_at IS NULL`: two other subqueries keep alias b covered, and
    the census must still name the one it no longer covers."""
    path = os.path.join(API, "main.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("_PC_TRADE_DEAD_SQL = ")
    end = src.index("\n_PC_TRADE_VOID_REASON_SQL = ", start)
    block = src[start:end]
    call = "{player_ban_active_sql('b')}"
    assert block.count(call) == 3, block.count(call)
    mutated = block.replace(call, "b.unbanned_at IS NULL", 1)
    readers, orm = scan_source("main.py", block)
    assert judge(readers, orm, whole_tree=False)[0] == [], "the unmutated constant must be covered"
    readers, orm = scan_source("main.py", mutated)
    problems, counts = judge(readers, orm, whole_tree=False)
    assert problems == [("reader without the definition", ("main.py", "<module>"), 1, ["b"])], problems
    assert counts["occurrences"] == 3, counts


@pytest.mark.parametrize("form", [
    "pb = aliased(PlayerBan)",
    "bans = relationship('PlayerBan')",
    "bans = relationship(PlayerBan, backref='player')",
    "bans = orm.relationship('PlayerBan')",
])
def test_tripwire_an_unmodelled_orm_form_fails_the_walk(form):
    readers, orm = scan_source("planted.py", form + "\n")
    problems, _ = judge(readers, orm, whole_tree=False)
    assert problems and problems[0][0] == "ORM form this walk does not model; extend the walk first", problems


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


# -- F3 R-e: every reader of pc_pool_members applies the definition ---------
#
# A snapshot freezes the pool; a member banned since it was taken is still a
# row in pc_pool_members. So every statement that reads that table either
# carries the pool's word (_PC_POOL_MEMBER_SQL, which carries the definition
# for the member's account) or is listed here with the reason it need not.
# Derived like the ban readers above: every non-docstring literal naming the
# table, judged inside its root expression. A site is keyed by its function,
# or by the constant it is assigned to at module level.
POOL_TABLE = re.compile(r"\bpc_pool_members\b")
POOL_WORD = "_PC_POOL_MEMBER_SQL"
POOL_ALLOWED = {
    ("main.py", "_PC_MEMBER_INSERT_SQL"): (
        1, "the snapshot's own insert (a writer); its rows come from the pool CTE, which carries the word"),
    ("main.py", "_PC_MEMBER_AT_SQL"): (
        1, "the open's pick inside the snapshot it rolls from; _pc_roll_prints follows every pick with "
           "_PC_LIVE_POOL_CHECK_SQL (the word, now) and re-rolls a refused member before any debit"),
    ("main.py", "_pc_roll_prints"): (
        1, "the band sizes of the same frozen rows the pick indexes by OFFSET; sizes filtered by the word "
           "would index a different row set than the pick reads, and a banned member counted here is a "
           "slot the live check re-rolls"),
    ("main.py", "_pc_steam_claim"): (
        1, "ordering only: the pool rank orders the portrait queue inside a WHERE that is "
           "_PC_STEAM_ELIGIBLE_SQL, which carries the definition; nothing about membership is answered"),
    ("main.py", "_pc_preview_read"): (
        1, "the member read after the subject read of the same player, which carries the word and "
           "returns None before this read when the word refuses"),
    ("main.py", "delete_player_data"): (
        1, "the account deletion's own delete of the account's rows"),
}


def _site(node, parents):
    q = _qualname(node, parents)
    if q != "<module>":
        return q
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
    return q


def pool_readers(module, src):
    """(module, site) -> [(lineno, carries the word)] per root naming the table."""
    tree = ast.parse(src)
    parents = _parents(tree)
    out, seen = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and POOL_TABLE.search(node.value):
            if _bare_string(node, parents):
                continue
            root = _root(node, parents)
            if id(root) in seen:
                continue
            seen.add(id(root))
            carries = any((isinstance(n, ast.Name) and n.id == POOL_WORD) or _definition_alias(n) is not None
                          for n in ast.walk(root))
            out.setdefault((module, _site(node, parents)), []).append((root.lineno, carries))
    return out


def judge_pool(readers, whole_tree=True):
    problems, counts = [], {"roots": 0, "carry": 0, "allowed": 0}
    for key, roots in sorted(readers.items()):
        counts["roots"] += len(roots)
        bare = [ln for ln, carries in roots if not carries]
        counts["carry"] += len(roots) - len(bare)
        if key in POOL_ALLOWED:
            if len(bare) != POOL_ALLOWED[key][0]:
                problems.append(("allowed count moved", key, POOL_ALLOWED[key][0], bare))
            counts["allowed"] += len(bare)
        else:
            problems.extend(("pool reader without the word", key, ln) for ln in bare)
    for key in (POOL_ALLOWED if whole_tree else ()):
        if key not in readers:
            problems.append(("allowed site gone", key))
    return problems, counts


def test_every_reader_of_the_pool_members_applies_the_definition(capsys):
    readers = {}
    for name, path in _modules():
        with open(path, encoding="utf-8") as fh:
            readers.update(pool_readers(name, fh.read()))
    problems, counts = judge_pool(readers)
    with capsys.disabled():
        print("\n[pool-readers] roots %(roots)d carry-the-word %(carry)d allowed %(allowed)d" % counts)
    assert not problems, problems
    assert counts["carry"] >= 2 and ("main.py", "internal_pc_card") in readers \
        and ("main.py", "pc_pool_summary") in readers, (counts, sorted(readers))


def test_the_pool_word_and_the_allowed_readers_reasons_hold():
    """The facts the allow-list's reasons rest on, as code: the word carries
    the definition for the member's account; the roll re-checks every pick
    with it; the portrait queue's WHERE carries the definition; the preview
    gates on the word before its member read."""
    import inspect
    import sys
    sys.path.insert(0, API)
    import main
    import models
    word = main._PC_POOL_MEMBER_SQL
    assert ("NOT EXISTS (SELECT 1 FROM player_bans b WHERE b.steam_id = p.steam_id AND "
            + models.player_ban_active_sql("b") + ")") in word
    assert word in main._PC_LIVE_POOL_CHECK_SQL
    roll = inspect.getsource(main._pc_roll_prints)
    assert roll.index("text(_PC_MEMBER_AT_SQL)") < roll.index("text(_PC_LIVE_POOL_CHECK_SQL)")
    assert "if live is None:\n                continue" in roll
    assert models.player_ban_active_sql("b") in main._PC_STEAM_ELIGIBLE_SQL
    assert "where = _PC_STEAM_ELIGIBLE_SQL" in inspect.getsource(main._pc_steam_claim)
    prev = inspect.getsource(main._pc_preview_read)
    assert prev.index("+ _PC_POOL_MEMBER_SQL)") < prev.index("FROM pc_pool_members m")
    assert prev.index("if sub is None") < prev.index("FROM pc_pool_members m")


def test_negative_control_a_pool_reader_without_the_word_is_reported():
    src = '''
async def planted(db):
    await db.execute(text("SELECT m.pool_rank FROM pc_pool_members m WHERE m.player_id = :p AND " + _PC_POOL_MEMBER_SQL))
    await db.execute(text("SELECT m.pool_rank FROM pc_pool_members m WHERE m.player_id = :p"))
'''
    problems, counts = judge_pool(pool_readers("planted.py", src), whole_tree=False)
    assert problems == [("pool reader without the word", ("planted.py", "planted"), 4)], problems
    assert counts == {"roots": 2, "carry": 1, "allowed": 0}, counts
