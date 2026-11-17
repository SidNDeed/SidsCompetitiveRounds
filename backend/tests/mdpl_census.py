"""MDPL point 5: the census of the circles an account deletion can close through
a players row, computed from the source (main.py, every other backend/api
module that runs SQL, models.py and the sql migrations are read as text;
nothing is imported or run).

Six module-level switches widen or sharpen what is read; all six off is the
census as first frozen (main.py alone, no triggers, no insert waits, the FOR
clause read from the last SELECT before it, foreign keys by table, a Player
known by select(Player)/get(Player) alone), kept as mdpl_census_base.json,
which test_mdpl_census computes again with the six off (the regression
control of the widening):
- MODULES: every backend/api/*.py that calls text(...) or .execute /
  .exec_driver_sql / .with_for_update (models.py and schemas.py keep their
  roles) is parsed. main.py's functions keep their bare names; module M's are
  "M:name" and "M:outer.inner". A bare-name call reaches the def Python's
  scoping gives it in its own module, else the def a `from X import name` in
  its scope (the function's own imports, its enclosing functions', the
  module's) names; `A.name(...)` reaches module X's def when A is an alias of X
  in scope (`import X [as A]`, also inside a function), a local assigned from
  a zero-argument function that imports X and returns it (main.py's
  _mrw_mod), or such a call itself. A statement reads its names in its own
  module (and constants a `from X import` brings); call-site parameter texts
  are keyed by the qualified name. Entries add every module's routes
  (functions decorated @R.<method>(...), R a module-level APIRouter(...)) and
  functions that open their own session (OPENERS by name or as an attribute,
  database.async_session()).
- TRIGGERS: a statement that INSERTs, UPDATEs (of the trigger's columns, when
  it names them and the statement's are read) or DELETEs a table fires the
  triggers the numbered migrations leave on it (in file order; the last
  CREATE of a trigger or function wins; a DROP TRIGGER with no later CREATE
  removes it; rollback files are not applied; WHEN conditions are not read: a
  trigger always fires); the locks of the statements in the trigger function's
  body come right after the statement's own, at its place, and fire their own
  triggers in turn. ORM forms fire too (update(M) and delete(M) every trigger
  of the event, M(...) an INSERT's, a store on a loaded Player an UPDATE OF
  that column's). A body with dynamic SQL (EXECUTE) is listed in unread.
- INSERT_WAITS: mode INS (conflicts only with INS: an in-flight insert of a
  key, named by table, so two inserts of one table always conflict). Every
  INSERT INTO T (and every ORM M(...)) holds (T, INS) from there on without
  waiting; an INSERT with ON CONFLICT (DO NOTHING or DO UPDATE) also first
  waits for it (a blocking (T, INS)). An upsert keeps its (T, NO KEY UPDATE).
  A plain INSERT waits too when it meets another transaction's in-flight row
  with the same unique key; holding it without a wait is, for step 1, a
  premise test_mdpl_census reads: after phase A the deletion's plain inserts
  are into gold_transactions alone, whose one unique key is its generated id.
- FOR_DEPTH: a FOR clause locks the tables of its own query: the FROM/JOIN
  items at its parenthesis depth after the nearest SELECT at that depth in its
  parenthesis group (a subquery between them does not count; a CTE body is its
  own group); FOR ... OF resolves its aliases at that depth first.
- FK_COLUMNS: foreign keys by column, from models.py (a Column's name, its
  ForeignKey, its default/server_default) and the .sql files (column
  REFERENCES, FOREIGN KEY (cols) REFERENCES, ALTER TABLE ... ADD [COLUMN] /
  ADD [CONSTRAINT] FOREIGN KEY, DEFAULT / SET DEFAULT). PostgreSQL checks a
  foreign key (a KEY SHARE on the parent row) only when the new row's value
  is not NULL, so an INSERT takes it when its column list names one of the
  key's columns, a column has a DEFAULT, or it has no column list; an ORM
  M(...) by its keyword arguments that are not None; an UPDATE SET, a DO
  UPDATE SET or an ORM store on a loaded Player that sets a foreign-key
  column to anything but the literal NULL/None takes it after the
  statement's own lock. A REFERENCES that cannot be placed on a column keeps
  its table on the table-level reading (every INSERT locks every parent).
  Off: every INSERT of a table locks every parent table of its foreign keys.
  The foreign keys a migration drops by dynamic SQL are named in
  FK_DROPPED_DYNAMIC by the selector of the migration's own pg_constraint
  lookup (every key of the table that references a parent, or that covers a
  column) and removed after every file is read (Source.fk_dropped; the files
  that added each key read are in Source.fk_origin).
- ORM_TYPES: an ORM store on a Player is a players-row write. A name holds a
  Player when it is loaded by select(Player)/get(Player) (as before), or is
  (1) a parameter or an annotated assignment naming Player (Optional[Player],
  "Player", Player | None), (2) assigned (awaited or not) from a call to a
  function whose return annotation names Player (an element of a tuple[...]
  return, unpacked), (3) a loop target over a tracked name or over select(Player),
  (4) assigned from a tracked name. Every other store of a models.Player
  column, `X.attr = ...` in any function or method of a read module whose X is
  neither tracked nor known as another model that has that column, is listed
  in Source.untyped and measured as "untyped", never skipped silently.

The deletion (delete_player_data) holds its own players row from its first
write of it (`UPDATE players SET pc_shards = 0`, FOR NO KEY UPDATE) to its
commit (phase A); from its tombstone store (`player.steam_id = ...`, a column
with a unique index, so FOR UPDATE at the flush autoflush brings right after)
every lock on that row waits for it, a foreign key's FOR KEY SHARE included
(phase B). A route closes a circle with it when, holding a row the deletion
waits for later, it then waits for that players row. The census lists every
place that can happen:

1. STEP 1, per phase: the deletion's blocking waits after the phase starts,
   in its flattened order (helpers inlined; SKIP LOCKED, NOWAIT and the try
   form of an advisory key never wait), as (table, lock mode). An advisory
   key is the table "key:<its argument>". Not waits: its own row and its own
   identity key, which it holds, and a bet party's row right after the
   no-wait guard on it (test_mdpl_bound's
   test_every_players_statement_the_deletion_reaches_is_classed classes each
   players statement of the reach that way); the one own-row wait is the
   tombstone's upgrade, which waits only for a FOR KEY SHARE holder of the
   row (any other holder would have made its first write wait).
2. Every statement read (main.py's, and with MODULES every read module's)
   that waits for a players row (SQL, SQLAlchemy
   forms, an ORM store on a loaded Player, a foreign key's FOR KEY SHARE on
   the players row an INSERT names), each ENTRY that reaches it (a route,
   or a function that opens its own session), and the step-1 tables that
   entry can hold there: its blocking locks earlier in its flattened order,
   in a mode that conflicts with the deletion's at that table (a loop's
   locks count as earlier for everything in the loop).
3. Rows are (the statement's place, the phase, the held tables), with their
   entries. Each gets one class: CLEAR (it holds none: computed), KEY (an
   identity key is taken before the statement and before every held lock:
   computed, the place named), UPGRADE (computed: the one held lock that
   conflicts is a FOR KEY SHARE on a players row, a foreign key naming the
   player, against the tombstone's upgrade; its circle and outcome are the
   scene test_a_route_that_named_the_player_in_an_insert_and_a_deletion_both_finish)
   or READ (a judgement by hand, frozen with its sentence in
   mdpl_census_frozen.json). A site (a statement's place) takes the highest
   class of its rows: READ > UPGRADE > KEY > CLEAR. KEY is read from the
   key's form alone (lesson 732): the key closes no circle only when it is
   the key of the player whose row the statement waits for, which the reader
   cannot see. So each row also carries its FALLBACK, the class it computes
   without its key (UPGRADE or READ for a KEY row, its class otherwise), and
   a site the highest of its rows'; a site whose fallback is above its class
   rests on a key, and its frozen record names whose key covers whose row
   ("covers") or is judged to its fallback by hand ("judged", with its "why").
4. Every statement whose SQL text the reader cannot read is listed
   (Source.unread) and frozen with its judgement, never skipped silently.

Places are named by function (qualified as above), the statement's text
(whitespace collapsed, first 72 characters) and its occurrence in that
function, never by line, so an edit elsewhere in a file does not move a row.
A trigger's locks carry the place of the statement that fires it.

Over-approximations, all toward more rows: every branch is taken; a callee's
statements are the caller's (except one that opens its own session, or runs
as a task); a call by bare name reaches the def Python's scoping gives it (a
def nested in the caller or one enclosing it, else a module-level def); a
dynamic text is every value its call sites, its loop, its dictionary, its
`if v not in X: raise` guard, an if-expression or a helper's return can give,
several statements' texts read as one (joined by " ;; "), or "?" (which
conflicts with every table); an advisory key is named by its argument's form,
not its value, so two keys of one form always conflict; commits inside an
entry are ignored.

Run as a script for the measured counts: python mdpl_census.py [--rows];
python mdpl_census.py --freeze rewrites mdpl_census_frozen.json from the
measure, keeping every judgement (a READ site's "why", a keyed site's
"covers" or "judged" and "why", an unread statement's and an untyped store's
reason); a new READ site, unread statement or untyped store is written with
an empty one, which the test refuses, and a new keyed site with none, which
the test refuses too.
"""
import ast
import itertools
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))

DELETION = "delete_player_data"
PHASE_A_MARK = "UPDATE players SET pc_shards = 0 WHERE id = :pid"
PHASE_B_HEAD = "ORM player.steam_id ="

OWN_ROW_FNS = frozenset({"delete_player_data", "_pc_clear_portrait_unit"})
GUARDED_FNS = frozenset({"_deletion_lock_party_row", "_credit_bet_fighter_tax", "_return_stake_exactly",
                         "_reconcile_team_series_bets", "_settle_ffa_bets_for_game"})
OWN_KEY_FNS = frozenset({"delete_player_data"})

SPAWNERS = frozenset({"create_task", "ensure_future", "add_task", "_spawn_confirm", "_spawn_confirm_hmac"})
OPENERS = frozenset({"async_session", "session_factory", "release_session", "asm_session"})
ROUTE_METHODS = frozenset({"get", "post", "put", "delete", "patch", "api_route", "websocket"})
KEY_COLUMNS = {"players": frozenset({"id", "steam_id", "discord_id"})}
IDENTITY_KEYS = frozenset({"key:hashtext(:p)"})

# The six widenings of the census, each a switch (all off = the census as first
# frozen, mdpl_census_base.json: main.py alone, no triggers, no insert waits, the
# FOR clause of the last SELECT, a foreign key's parent locked by every INSERT of
# its table, a Player known by select(Player)/get(Player) alone).
MODULES = True          # every backend/api module that runs SQL is read, not main.py alone
TRIGGERS = True         # a write fires the triggers backend/sql defines on its table
INSERT_WAITS = True     # an INSERT holds (table, INS); one with ON CONFLICT waits for it
FOR_DEPTH = True        # a FOR clause locks its own query's tables (its parenthesis depth), not a subquery's
FK_COLUMNS = True       # a foreign key's KEY SHARE only when the write sets one of its columns
ORM_TYPES = True        # a Player object is also known by annotation, return type, loop and copy; the rest is listed

# Foreign keys a migration drops by dynamic SQL (EXECUTE format('ALTER TABLE ...
# DROP CONSTRAINT %I', ...) over a pg_constraint lookup), which the reader cannot
# read: (table, selector, value) -> the migration, the selector being the
# lookup's own: "parent" (every foreign key of the table that references the
# table `value`) or "column" (every foreign key of the table that covers the
# column `value`). Applied after every file (FK_COLUMNS); test_mdpl_census reads
# each lookup and checks that no later migration adds a selected key again.
FK_DROPPED_DYNAMIC = {
    ("admin_actions", "parent", "admin_users"): "192_chat_moderation.sql",    # its EXECUTE at line 90
    ("mail_messages", "column", "in_reply_to"): "415_mail_send_receipts.sql",    # its EXECUTE at line 380
}
# Triggers a migration creates or drops by dynamic SQL: none (the sweep of every
# numbered migration's EXECUTE found no CREATE or DROP TRIGGER in one).
TRIGGERS_DYNAMIC = {}
SKIP_MODULES = frozenset({"main", "models", "schemas"})     # main is read always; models and schemas keep their roles

# Row-lock modes; CONFLICTS[held] = the modes a waiter is refused in. INS is an
# in-flight insert of a key: an INSERT ... ON CONFLICT waits for another
# transaction's insert of the same key (named by table, so any two conflict).
KS, SH, NKU, UPD, OWN_UP, INS = "KEY SHARE", "SHARE", "NO KEY UPDATE", "UPDATE", "UPDATE OWN ROW", "INS"
CONFLICTS = {
    KS: frozenset({UPD, OWN_UP}),
    SH: frozenset({NKU, UPD}),
    NKU: frozenset({SH, NKU, UPD}),
    UPD: frozenset({KS, SH, NKU, UPD}),
    "KEY": frozenset({"KEY"}),
    INS: frozenset({INS}),
}
# An event's third field: True (a blocking wait), False (SKIP LOCKED, NOWAIT, a
# try key: never waits, never counted) or HELD (held from there on, never a wait:
# a plain INSERT's own key).
HELD = "held"

_W = r"[A-Za-z_][A-Za-z0-9_]*"
_PH = r"\{\?[^}]*\}"
_TB = r"((?:[A-Za-z_]|" + _PH + r")(?:[A-Za-z0-9_]|" + _PH + r")*)"   # one way to match each character: no backtracking blow-up
RX_UPDATE = re.compile(r"(?<!FOR )(?<!KEY )(?<!DO )\bUPDATE (?:ONLY )?" + _TB
                       + r"(?: AS " + _W + r"| (?!SET\b)" + _W + r")? SET (.*?)(?= WHERE | FROM | RETURNING |$)", re.I)
RX_DELETE = re.compile(r"\bDELETE FROM (?:ONLY )?" + _TB, re.I)
RX_INSERT = re.compile(r"\bINSERT INTO " + _TB, re.I)
RX_UPSERT = re.compile(r"\bINSERT INTO " + _TB + r"(?:(?!;).)*?\bDO UPDATE\b", re.I)
RX_FOR = re.compile(r"\bFOR (NO KEY UPDATE|UPDATE|KEY SHARE|SHARE)\b(?: OF (" + _W + r"(?:, ?" + _W
                    + r")*))?( SKIP LOCKED| NOWAIT)?", re.I)
RX_FROM = re.compile(r"\b(?:FROM|JOIN) (?:ONLY )?" + _TB, re.I)
RX_SELECT = re.compile(r"\bSELECT\b", re.I)
RX_ALIAS = re.compile(r"\b(?:FROM|JOIN|UPDATE) (?:ONLY )?" + _TB + r"(?: AS)? (?!(?:WHERE|ON|JOIN|LEFT|RIGHT|"
                      r"INNER|FULL|CROSS|USING|ORDER|GROUP|LIMIT|FOR|SET|WHEN|AND|OR|NATURAL|LATERAL|WITH|"
                      r"UNION|RETURNING|HAVING|OFFSET|SELECT|VALUES)\b)(" + _W + r")\b", re.I)
RX_KEY = re.compile(r"\bpg_(try_)?advisory_(?:xact_)?lock(?:_shared)?\((.*)", re.I)
RX_ON_CONFLICT = re.compile(r"\bINSERT INTO " + _TB + r"(?:(?!;).)*?\bON CONFLICT\b", re.I)
RX_DO_UPDATE = re.compile(r"\bINSERT INTO " + _TB + r"(?:(?!;).)*?\bDO UPDATE SET (.*?)(?= WHERE | RETURNING |;|$)",
                          re.I)
# backend/sql: triggers and their functions.
RX_TRIGGER = re.compile(r"\bCREATE (?:OR REPLACE )?(?:CONSTRAINT )?TRIGGER\s+(" + _W + r")\s+(BEFORE|AFTER|INSTEAD OF)"
                        r"\s+(.*?)\s+ON\s+(?:ONLY\s+)?(?:" + _W + r"\.)?(" + _W + r")\b(.*?)\bEXECUTE\s+"
                        r"(?:FUNCTION|PROCEDURE)\s+(?:" + _W + r"\.)?(" + _W + r")\s*\(", re.I | re.S)
RX_DROP_TRIGGER = re.compile(r"\bDROP TRIGGER\s+(?:IF EXISTS\s+)?(" + _W + r")\s+ON\s+(?:ONLY\s+)?(?:" + _W
                             + r"\.)?(" + _W + r")\b", re.I)
RX_FUNCTION = re.compile(r"\bCREATE (?:OR REPLACE )?FUNCTION\s+(?:" + _W + r"\.)?(" + _W + r")\s*\(([^)]*)\)(.*?)"
                         r"(\$[A-Za-z0-9_]*\$)(.*?)\4", re.I | re.S)
RX_DYNAMIC = re.compile(r"\bEXECUTE\b(?!\s+(?:FUNCTION|PROCEDURE)\b)", re.I)


def _norm(s):
    return " ".join(s.split())


def _balanced(s):
    """A call's argument text: `s` starts right after its '('."""
    depth = 1
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[:i]
    return s


def key_name(arg):
    """An advisory key's table name. Binds become ':p', so the identity key's
    two spellings (`hashtext(:sid)`, `hashtext(CAST(:sid AS text))`) are one."""
    a = re.sub(r":" + _W, ":p", _norm(arg))
    a = re.sub(r"CAST\((:p) AS text\)", r"\1", a, flags=re.I)
    return "key:" + a


def conflicts(held_mode, wait_mode):
    return wait_mode in CONFLICTS.get(held_mode, ())


def _own_nodes(fn):
    """A function's own nodes: not a nested def's, class's or lambda's."""
    todo = list(ast.iter_child_nodes(fn))
    own = []
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        own.append(n)
        todo.extend(ast.iter_child_nodes(n))
    return own


def _runs_sql(tree):
    """A module runs SQL: it calls text(...), or .execute / .exec_driver_sql /
    .with_for_update on something."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name) and n.func.id == "text" and n.args:
                return True
            if isinstance(n.func, ast.Attribute) and n.func.attr in ("execute", "exec_driver_sql", "with_for_update"):
                return True
    return False


def mod_of(q):
    """The module of a qualified function name: 'M:name' is module M's, a bare one main.py's."""
    return q.split(":", 1)[0] if ":" in q else "main"


def qn(mod, name):
    return name if mod == "main" else "%s:%s" % (mod, name)


class Source:
    """The functions, constants and models of main.py and (MODULES) of every
    other backend/api module that runs SQL, and (TRIGGERS) backend/sql's
    triggers, read once."""

    def __init__(self, api=API, sql_dir=SQL_DIR, main_text=None):
        if main_text is None:
            with open(os.path.join(api, "main.py"), encoding="utf-8") as fh:
                main_text = fh.read()
        self.tree = ast.parse(main_text)
        self.trees = {"main": self.tree}
        if MODULES:
            for fn in sorted(os.listdir(api)):
                stem = fn[:-3]
                if not fn.endswith(".py") or stem in SKIP_MODULES or not re.fullmatch(_W, stem):
                    continue
                with open(os.path.join(api, fn), encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                if _runs_sql(tree):
                    self.trees[stem] = tree
        self._cur = "main"                      # the module whose names a text is read in
        self._ns = {}
        with open(os.path.join(api, "models.py"), encoding="utf-8") as fh:
            mtree = ast.parse(fh.read())
        self.defs = {}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.defs.setdefault(node.name, node)
        for node in self.tree.body:             # a module-level def wins over a nested one of its name
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.defs[node.name] = node
        self.top = {n.name for n in self.tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.qdefs = {}                         # "outer.inner" -> a def nested in a function

        def nested(stmts):
            for st in stmts:
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield st
                    continue
                if isinstance(st, ast.ClassDef):
                    continue
                for field in ("body", "orelse", "finalbody"):
                    sub = getattr(st, field, None)
                    if isinstance(sub, list):
                        yield from nested(sub)
                for h in getattr(st, "handlers", []) or []:
                    yield from nested(h.body)
                if type(st).__name__ == "Match":
                    for case in st.cases:
                        yield from nested(case.body)

        def collect(fn, qual):
            for sub in nested(fn.body):
                q = qual + "." + sub.name
                self.qdefs.setdefault(q, sub)
                collect(sub, q)
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                collect(node, node.name)
        for m, tree in self.trees.items():      # another module's functions: "M:name", "M:outer.inner"
            if m == "main":
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.defs[qn(m, node.name)] = node
                    self.top.add(qn(m, node.name))
                    collect(node, qn(m, node.name))
        self._modules, self._ret_active, self._fn_stack = {}, set(), []
        self.api = api
        self.mimports, self.fimports, self.modfns = {}, {}, {}
        if MODULES:
            self._read_imports()
        for _pass in range(2 if MODULES else 1):     # twice: a module's constant may read another's
            for m, tree in self.trees.items():
                self._cur = m
                for node in tree.body:
                    if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                            and isinstance(node.targets[0], ast.Name):
                        self._const(node.targets[0].id, node.value)
                    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                            and node.value is not None:
                        self._const(node.target.id, node.value)
        self._cur = "main"
        self.models, self.fks = {}, defaultdict(set)
        for node in mtree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            tn = None
            for st in node.body:
                if isinstance(st, ast.Assign) and any(getattr(t, "id", "") == "__tablename__" for t in st.targets) \
                        and isinstance(st.value, ast.Constant):
                    tn = st.value.value
            if tn:
                self.models[node.name] = tn
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "ForeignKey" and sub.args \
                            and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                        self.fks[tn].add(sub.args[0].value.split(".")[0])
        rx_create = re.compile(r"CREATE TABLE (?:IF NOT EXISTS )?(" + _W + r") \((.*?)\);", re.I | re.S)
        rx_alter = re.compile(r"ALTER TABLE (?:ONLY )?(?:IF EXISTS )?(" + _W + r")\b([^;]*)", re.I)
        rx_ref = re.compile(r"\bREFERENCES (" + _W + r")", re.I)
        for fn in sorted(os.listdir(sql_dir)):
            if fn.endswith(".sql"):
                with open(os.path.join(sql_dir, fn), encoding="utf-8", errors="replace") as fh:
                    body = re.sub(r"--[^\n]*", " ", fh.read())
                for m in itertools.chain(rx_create.finditer(body), rx_alter.finditer(body)):
                    for r in rx_ref.finditer(m.group(2)):
                        self.fks[m.group(1).lower()].add(r.group(1).lower())
        self.fkcols, self.fk_defaults, self.fk_fallback = defaultdict(set), defaultdict(set), defaultdict(set)
        self.model_cols, self.fk_counts, self.fk_unplaced = {}, {}, []
        # (table, columns, parent) -> the files that add the key; -> the migration that drops it by dynamic SQL
        self.fk_origin, self.fk_dropped = defaultdict(set), {}
        if FK_COLUMNS:
            self._read_fk_columns(mtree, sql_dir, rx_create, rx_alter, rx_ref)
        self.triggers = self._read_triggers(sql_dir) if TRIGGERS else {}
        self.roots = self._roots()
        self.params = self._param_values_q() if MODULES else self._param_values()
        self._memo = {}
        self.unread = set()                     # "fn | text(arg)" of every statement whose SQL is unreadable
        self.untyped, self.untyped_why, self.track_counts = set(), {}, defaultdict(int)
        if ORM_TYPES:
            self.model_attrs = self._model_attrs(mtree)
            self._untyped_pass()

    # -- modules -------------------------------------------------------------

    def _space(self, m):
        if m not in self._ns:
            self._ns[m] = {"consts": {}, "dicts": defaultdict(set), "dictvals": {}, "listvals": {}}
        return self._ns[m]

    # The current module's constants (main.py's outside a flattening).
    consts = property(lambda self: self._space(self._cur)["consts"])
    dicts = property(lambda self: self._space(self._cur)["dicts"])
    dictvals = property(lambda self: self._space(self._cur)["dictvals"])
    listvals = property(lambda self: self._space(self._cur)["listvals"])

    def _import_targets(self, node):
        """{bound name: ("mod", X) | ("name", X, n)} of an import of an api module."""
        out = {}
        known = lambda x: x == "main" or x in self.trees or (    # noqa: E731
            re.fullmatch(_W, x) is not None and os.path.exists(os.path.join(self.api, x + ".py")))
        if isinstance(node, ast.Import):
            for a in node.names:
                if known(a.name):
                    out[a.asname or a.name] = ("mod", a.name)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module and known(node.module):
            for a in node.names:
                if a.name != "*":
                    out[a.asname or a.name] = ("name", node.module, a.name)
        return out

    def _all_fns(self):
        return [(q, self.defs[q]) for q in self.top] + list(self.qdefs.items())

    def _read_imports(self):
        """Module-level imports (also under try/if), every function's own
        imports, and the functions that import a module and return it."""
        for m, tree in self.trees.items():
            imp = {}
            todo = list(tree.body)
            while todo:
                n = todo.pop(0)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    imp.update(self._import_targets(n))
                    continue
                todo.extend(x for x in ast.iter_child_nodes(n) if isinstance(x, ast.stmt))
                for h in getattr(n, "handlers", []) or []:
                    todo.extend(h.body)
            self.mimports[m] = imp
        for q, node in self._all_fns():
            imp = {}
            own = _own_nodes(node)
            for n in sorted((x for x in own if isinstance(x, (ast.Import, ast.ImportFrom))),
                            key=lambda x: (x.lineno, x.col_offset)):
                imp.update(self._import_targets(n))
            self.fimports[q] = imp
            a = node.args
            if a.args or a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg:
                continue
            rets = [x for x in own if isinstance(x, ast.Return)]
            mods = {imp.get(r.value.id, ("",))[1] if isinstance(r.value, ast.Name)
                    and imp.get(r.value.id, ("",))[0] == "mod" else None for r in rets}
            if rets and len(mods) == 1 and None not in mods and next(iter(mods)) in self.trees:
                self.modfns[q] = next(iter(mods))

    def _scope(self, caller):
        """The import tables a name in `caller` sees, innermost first."""
        m = mod_of(caller) if caller else self._cur
        out = []
        if caller:
            q = caller
            while True:
                out.append(self.fimports.get(q, {}))
                local = q.split(":", 1)[1] if ":" in q else q
                if "." not in local:
                    break
                q = q.rsplit(".", 1)[0]
        out.append(self.mimports.get(m, {}))
        return out

    def _imported(self, name, caller=None):
        caller = caller if caller is not None else (self._fn_stack[-1] if self._fn_stack else None)
        for imp in self._scope(caller):
            if name in imp:
                return imp[name]
        return None

    def _imported_value(self, name, kind):
        """A constant `from X import name` brings (X an api module), of `kind`."""
        t = self._imported(name)
        if t and t[0] == "name" and t[1] in self.trees:
            return self._space(t[1])[kind].get(t[2])
        return None

    def _alias_mod(self, name, caller=None, modvars=None):
        """The api module a name in `caller` stands for, or None."""
        if modvars and name in modvars:
            return modvars[name]
        t = self._imported(name, caller)
        return t[1] if t and t[0] == "mod" else None

    def _attr_target(self, func, caller, modvars=None):
        """The function `A.name(...)` reaches: A a module's alias, a local
        assigned from a function that returns a module, or such a call."""
        if not isinstance(func, ast.Attribute):
            return None
        v, mod = func.value, None
        if isinstance(v, ast.Name):
            mod = self._alias_mod(v.id, caller, modvars)
        elif isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and not v.args and not v.keywords:
            f = self.resolve(caller, v.func.id) if caller else None
            mod = self.modfns.get(f)
        if mod is None or mod not in self.trees:
            return None
        q = qn(mod, func.attr)
        return q if q in self.top else None

    # -- foreign keys by column -------------------------------------------------

    @staticmethod
    def _split_top(s):
        """`s` split at its commas outside parentheses and '...'."""
        out, d, quoted, cur = [], 0, False, []
        for ch in s:
            if ch == "'":
                quoted = not quoted
            elif not quoted and ch == "(":
                d += 1
            elif not quoted and ch == ")":
                d -= 1
            if ch == "," and d == 0 and not quoted:
                out.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        out.append("".join(cur))
        return [x.strip() for x in out if x.strip()]

    def _read_fk_columns(self, mtree, sql_dir, rx_create, rx_alter, rx_ref):
        """self.fkcols {table: {(columns, parent)}}, self.fk_defaults {table:
        columns with a DEFAULT}, self.model_cols {model: {attribute: column}};
        a REFERENCES not placed on a column puts its table in self.fk_fallback
        (today's table-level reading) and in self.fk_unplaced."""
        cnt = {"models.py": [0, 0], ".sql": [0, 0]}          # [read, placed on a column]
        for node in mtree.body:
            if not isinstance(node, ast.ClassDef) or node.name not in self.models:
                continue
            tn, cols, placed = self.models[node.name], {}, set()
            for st in node.body:
                tgt = st.targets[0] if isinstance(st, ast.Assign) and len(st.targets) == 1 else (
                    st.target if isinstance(st, ast.AnnAssign) else None)
                v = getattr(st, "value", None)
                if not isinstance(tgt, ast.Name) or not isinstance(v, ast.Call) \
                        or getattr(v.func, "id", getattr(v.func, "attr", "")) not in ("Column", "mapped_column"):
                    continue
                col = next((a.value for a in v.args if isinstance(a, ast.Constant) and isinstance(a.value, str)),
                           tgt.id).lower()
                cols[tgt.id] = col
                if any(k.arg in ("default", "server_default") and not (
                        isinstance(k.value, ast.Constant) and k.value.value is None) for k in v.keywords) \
                        or any(isinstance(a, ast.Call) and getattr(a.func, "id", "") in ("Identity", "Sequence")
                               for a in v.args):
                    self.fk_defaults[tn].add(col)
                for a in v.args:
                    if isinstance(a, ast.Call) and getattr(a.func, "id", "") == "ForeignKey" and a.args \
                            and isinstance(a.args[0], ast.Constant) and isinstance(a.args[0].value, str):
                        parent = a.args[0].value.split(".")[0].lower()
                        self.fkcols[tn].add(((col,), parent))
                        self.fk_origin[(tn, (col,), parent)].add("models.py")
                        placed.add(id(a))
            self.model_cols[node.name] = cols
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "ForeignKey" and sub.args \
                        and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                    cnt["models.py"][0] += 1
                    if id(sub) in placed:
                        cnt["models.py"][1] += 1
                    else:
                        self.fk_fallback[tn].add(sub.args[0].value.split(".")[0].lower())
                        self.fk_unplaced.append("models.py %s: %s" % (node.name, ast.unparse(sub)[:80]))
        rx_fk = re.compile(r"(?:CONSTRAINT \"?" + _W + r"\"? )?FOREIGN KEY ?\(([^)]*)\) ?REFERENCES (" + _W + r")",
                           re.I)
        rx_cons = re.compile(r"(?:CONSTRAINT \"?" + _W + r"\"? )?(?:PRIMARY KEY|UNIQUE|CHECK|EXCLUDE|LIKE)\b", re.I)
        rx_dflt = re.compile(r"\bDEFAULT\b|\b(?:SMALL|BIG)?SERIAL\b|\bGENERATED\b", re.I)

        def column_def(table, item, origin):
            """`col TYPE ...`: 1 when its REFERENCES is placed on the column; its DEFAULT."""
            cm = re.match(r"\"?(" + _W + r")\"? (.*)", item, re.S)
            refs = list(rx_ref.finditer(item))
            if not cm:
                return 0
            col = cm.group(1).lower()
            if rx_dflt.search(cm.group(2)):
                self.fk_defaults[table].add(col)
            if len(refs) == 1:
                self.fkcols[table].add(((col,), refs[0].group(1).lower()))
                self.fk_origin[(table, (col,), refs[0].group(1).lower())].add(origin)
                return 1
            return 0

        for fn in sorted(os.listdir(sql_dir)):
            if not fn.endswith(".sql"):
                continue
            with open(os.path.join(sql_dir, fn), encoding="utf-8", errors="replace") as fh:
                body = re.sub(r"--[^\n]*", " ", fh.read())
            for kind, rx in (("create", rx_create), ("alter", rx_alter)):
                for m in rx.finditer(body):
                    table = m.group(1).lower()
                    nref = len(rx_ref.findall(m.group(2)))
                    placed = 0
                    for item in self._split_top(_norm(m.group(2))):
                        if kind == "alter":
                            fm = re.match(r"ADD (" + rx_fk.pattern + r")", item, re.I)
                            if fm:
                                item = fm.group(1)
                            elif re.match(r"ALTER (?:COLUMN )?\"?" + _W + r"\"? SET DEFAULT\b", item, re.I):
                                self.fk_defaults[table].add(re.match(r"ALTER (?:COLUMN )?\"?(" + _W + r")",
                                                                     item, re.I).group(1).lower())
                                continue
                            elif re.match(r"ADD CONSTRAINT\b", item, re.I):
                                continue                # counted unplaced below if it carries a REFERENCES
                            else:
                                am = re.match(r"ADD (?:COLUMN )?(?:IF NOT EXISTS )?(.*)", item, re.I | re.S)
                                if am:
                                    placed += column_def(table, am.group(1), fn)
                                continue
                        fm = rx_fk.match(item)
                        if fm:
                            cols = tuple(c.strip().strip('"').lower() for c in fm.group(1).split(","))
                            self.fkcols[table].add((cols, fm.group(2).lower()))
                            self.fk_origin[(table, cols, fm.group(2).lower())].add(fn)
                            placed += 1
                        elif kind == "create" and not rx_cons.match(item):
                            placed += column_def(table, item, fn)
                    cnt[".sql"][0] += nref
                    cnt[".sql"][1] += placed
                    if placed < nref:
                        for r in rx_ref.finditer(m.group(2)):
                            self.fk_fallback[table].add(r.group(1).lower())
                        self.fk_unplaced.append("%s %s TABLE %s: %d of %d REFERENCES not placed" % (
                            fn, kind.upper(), table, nref - placed, nref))
        for (table, how, value), mig in FK_DROPPED_DYNAMIC.items():   # dropped by dynamic SQL, after every file
            assert how in ("parent", "column"), how
            gone = {(cols, p) for cols, p in self.fkcols.get(table, ())
                    if (p == value if how == "parent" else value in cols)}
            self.fkcols[table] = set(self.fkcols.get(table, ())) - gone
            for cols, p in gone:
                self.fk_dropped[(table, cols, p)] = mig
        self.fk_counts = cnt

    def _fk_map(self, table):
        """{column: {parent}} of a table's foreign keys."""
        out = {}
        for cols, parent in self.fkcols.get(table, ()):
            for c in cols:
                out.setdefault(c, set()).add(parent)
        return out

    def _insert_parents(self, table, cols):
        """The parents an INSERT naming `cols` (None: no column list) checks."""
        if not FK_COLUMNS or table in self.fk_fallback:
            return sorted(self.fks.get(table, ()))
        dflt = self.fk_defaults.get(table, set())
        return sorted({parent for fcols, parent in self.fkcols.get(table, ())
                       if cols is None or any(c in cols or c in dflt for c in fcols)})

    def _set_parents(self, table, assigns):
        """The parents an assignment list `c = v, ...` sets a foreign key of
        (v anything but the literal NULL)."""
        if not FK_COLUMNS:
            return []
        fk = self._fk_map(table)
        out = []
        for a in self._split_top(assigns):
            if "=" not in a:
                continue
            col, val = a.split("=", 1)
            col = col.strip().strip('"').lower()
            if col in fk and val.strip().upper() != "NULL":
                out.extend(sorted(fk[col]))
        return list(dict.fromkeys(out))

    @staticmethod
    def _insert_cols(s, end):
        """The column list of the INSERT whose table token ends at `end`, or None."""
        rest = s[end:].lstrip()
        am = re.match(r"(?:AS )?" + _W + r" (?=\()", rest, re.I)
        if am and not re.match(r"(?:SELECT|VALUES|DEFAULT)\b", rest, re.I):
            rest = rest[am.end():]
        if not rest.startswith("("):
            return None
        inner = _balanced(rest[1:])
        if re.match(r"\s*(?:SELECT|WITH|VALUES)\b", inner, re.I):
            return None
        return {c.strip().strip('"').lower() for c in inner.split(",")}

    # -- Player objects (ORM_TYPES) --------------------------------------------

    @staticmethod
    def _model_attrs(mtree):
        """{model class: its column attributes (Column / mapped_column)}."""
        out = {}
        for node in mtree.body:
            if isinstance(node, ast.ClassDef):
                attrs = set()
                for st in node.body:
                    tgt = st.targets[0] if isinstance(st, ast.Assign) and len(st.targets) == 1 else (
                        st.target if isinstance(st, ast.AnnAssign) else None)
                    v = getattr(st, "value", None)
                    if isinstance(tgt, ast.Name) and isinstance(v, ast.Call) \
                            and getattr(v.func, "id", getattr(v.func, "attr", "")) in ("Column", "mapped_column"):
                        attrs.add(tgt.id)
                out[node.name] = attrs
        return out

    @staticmethod
    def _ann_models(ann):
        """The model-like names an annotation names (Player, "Player", Optional[...], X | None, ...)."""
        out = []
        for n in ast.walk(ann) if ann is not None else ():
            if isinstance(n, ast.Name):
                out.append(n.id)
            elif isinstance(n, ast.Attribute):
                out.append(n.attr)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                out.extend(re.findall(_W, n.value))
        return out

    def _callee(self, call, fnq):
        """The def node a call (awaited or not) reaches, or None."""
        if isinstance(call, ast.Await):
            call = call.value
        if not isinstance(call, ast.Call):
            return None
        if isinstance(call.func, ast.Name):
            q = self.resolve(fnq, call.func.id)
        else:
            q = self._attr_target(call.func, fnq)
        return None if q is None else (self.qdefs.get(q) or self.defs.get(q))

    def _model_of_value(self, v, fnq):
        """The model a value is an instance of, when known: select(M)/get(M),
        M(...), or a call to a function whose return annotation names M."""
        val = v.value if isinstance(v, ast.Await) else v
        if isinstance(val, ast.Call) and getattr(val.func, "id", "") in self.models:
            return val.func.id
        for sub in ast.walk(v):
            if isinstance(sub, ast.Call) and sub.args and getattr(sub.args[0], "id", "") in self.models and (
                    getattr(sub.func, "id", "") == "select" or getattr(sub.func, "attr", "") == "get"):
                return sub.args[0].id
        node = self._callee(v, fnq)
        if node is not None:
            ms = [n for n in self._ann_models(node.returns) if n in self.models]
            if ms:
                return ms[0]
        return None

    def _player_params(self, fn):
        """Rule 1: the parameters annotated with Player (Optional[Player], "Player", Player | None, ...)."""
        a = fn.args
        return {p.arg for p in a.posonlyargs + a.args + a.kwonlyargs if "Player" in self._ann_models(p.annotation)}

    RESULT_ACCESSORS = frozenset({"scalar_one_or_none", "scalar_one", "scalar", "scalars", "first", "one",
                                  "one_or_none", "all", "unique"})

    def _holds_player(self, v, tracked):
        """Rule 4: a tracked name; `a if c else b` / `a or b` of tracked names
        (None allowed); or a result accessor on a tracked name
        (`res.scalar_one_or_none()`, `res.scalars().first()`, of a select(Player))."""
        if isinstance(v, ast.Await):
            v = v.value
        if isinstance(v, ast.Name):
            return v.id in tracked
        if isinstance(v, ast.IfExp):
            alts = [x for x in (v.body, v.orelse) if not (isinstance(x, ast.Constant) and x.value is None)]
            return bool(alts) and all(self._holds_player(x, tracked) for x in alts)
        if isinstance(v, ast.BoolOp) and isinstance(v.op, ast.Or):
            alts = [x for x in v.values if not (isinstance(x, ast.Constant) and x.value is None)]
            return bool(alts) and all(self._holds_player(x, tracked) for x in alts)
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr in self.RESULT_ACCESSORS:
            root = v.func.value
            while isinstance(root, ast.Call) and isinstance(root.func, ast.Attribute) \
                    and root.func.attr in self.RESULT_ACCESSORS:
                root = root.func.value
            return isinstance(root, ast.Name) and root.id in tracked
        return False

    def _player_track(self, st, tracked, fnq, others=None, rules=None):
        """Rules 2-4 (and select(Player)/get(Player), as before) on one
        statement: names that now hold a Player go into `tracked`; a name known
        to hold another model goes into `others` (name -> model)."""
        def add(name, rule):
            if name not in tracked:
                tracked.add(name)
                if rules is not None:
                    rules[name] = rule
        if isinstance(st, (ast.For, ast.AsyncFor)):
            it = st.iter
            root = it
            while isinstance(root, (ast.Call, ast.Attribute, ast.Await, ast.Subscript)):
                root = root.func if isinstance(root, ast.Call) else root.value
            if isinstance(st.target, ast.Name) and (
                    (isinstance(root, ast.Name) and root.id in tracked) or self._loads_player(it)):
                add(st.target.id, 3)
            elif isinstance(st.target, ast.Tuple) and isinstance(it, (ast.Tuple, ast.List)) and it.elts and all(
                    isinstance(e, ast.Tuple) and len(e.elts) == len(st.target.elts) for e in it.elts):
                for i, tg in enumerate(st.target.elts):     # for (p, x) in ((p1, a), (p2, b))
                    if isinstance(tg, ast.Name) and all(self._holds_player(e.elts[i], tracked) for e in it.elts):
                        add(tg.id, 3)
            return
        if isinstance(st, ast.Assign) and len(st.targets) == 1:
            tgt, v = st.targets[0], st.value
        elif isinstance(st, ast.AnnAssign) and st.value is not None:
            tgt, v = st.target, st.value
        else:
            return
        val = v.value if isinstance(v, ast.Await) else v
        if isinstance(tgt, ast.Name):
            if self._loads_player(v):
                add(tgt.id, 0)
            elif self._holds_player(val, tracked):
                add(tgt.id, 4)
            else:
                node = self._callee(v, fnq)
                if node is not None and "Player" in self._ann_models(node.returns):
                    add(tgt.id, 2)
                elif isinstance(st, ast.AnnAssign) and "Player" in self._ann_models(st.annotation):
                    add(tgt.id, 1)
            if others is not None and tgt.id not in tracked:
                m = self._model_of_value(v, fnq)
                if m is not None:
                    others[tgt.id] = m
        elif isinstance(tgt, ast.Tuple):
            node = self._callee(v, fnq)
            ret = getattr(node, "returns", None)
            if isinstance(ret, ast.Subscript) and self._ann_models(ret.value)[:1] in (["tuple"], ["Tuple"]):
                elts = ret.slice.elts if isinstance(ret.slice, ast.Tuple) else [ret.slice]
                for tg, el in zip(tgt.elts, elts):
                    if isinstance(tg, ast.Name) and "Player" in self._ann_models(el):
                        add(tg.id, 2)

    def _untyped_pass(self):
        """Every attribute store `X.attr = ...` (Assign, AugAssign) of a column
        of models.Player, in every function of every read module (methods
        included), whose X is not a tracked Player and not known to be an
        instance of another model that has that attribute: self.untyped."""
        pattrs = self.model_attrs.get("Player", set())
        for m, tree in self.trees.items():
            qmap = {id(node): q for q, node in self._all_fns() if mod_of(q) == m}
            for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
                for st in cls.body:
                    if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qmap.setdefault(id(st), qn(m, "%s.%s" % (cls.name, st.name)))
            for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                q = qmap.get(id(fn)) or qn(m, "<def>" + fn.name)
                own = sorted((n for n in _own_nodes(fn) if isinstance(n, ast.stmt)),
                             key=lambda n: (n.lineno, n.col_offset))
                params = {p.arg: p for p in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs}
                tracked, others, rules = set(), {}, {}
                for p in self._player_params(fn):
                    tracked.add(p)
                    rules[p] = 1
                for p, node in params.items():
                    ms = [x for x in self._ann_models(node.annotation) if x in self.models and x != "Player"]
                    if ms and p not in tracked:
                        others[p] = ms[0]
                for st in own:
                    self._player_track(st, tracked, q, others, rules)
                for r in rules.values():
                    self.track_counts[r] += 1
                for st in own:
                    tgts = st.targets if isinstance(st, ast.Assign) else (
                        [st.target] if isinstance(st, ast.AugAssign) else [])
                    for t in tgts:
                        if not (isinstance(t, ast.Attribute) and t.attr in pattrs):
                            continue
                        x = t.value
                        if isinstance(x, ast.Name) and x.id in tracked:
                            continue
                        if isinstance(x, ast.Name) and x.id in others and t.attr in self.model_attrs.get(
                                others[x.id], ()):
                            continue
                        key = "%s | ORM %s.%s =" % (q, ast.unparse(x), t.attr)
                        self.untyped.add(key)
                        self.untyped_why[key] = self._why_untracked(x, fn, own, params, others)

    def _why_untracked(self, x, fn, own, params, others):
        """Why the store's object is not tracked (for the report; not compared)."""
        if not isinstance(x, ast.Name):
            return "not a plain name (%s)" % type(x).__name__
        if x.id in others:
            return "known as %s, which has no such column" % others[x.id]
        if x.id in params:
            ann = params[x.id].annotation
            return "a parameter %s" % ("annotated %s" % ast.unparse(ann) if ann is not None else "without annotation")
        for st in own:
            if isinstance(st, (ast.For, ast.AsyncFor)) and isinstance(st.target, ast.Name) and st.target.id == x.id:
                return "a loop target over %s" % ast.unparse(st.iter)[:80]
            if isinstance(st, (ast.For, ast.AsyncFor)) and any(
                    isinstance(n, ast.Name) and n.id == x.id for n in ast.walk(st.target)):
                return "an unpacked loop target over %s" % ast.unparse(st.iter)[:80]
            if isinstance(st, ast.Assign) and any(isinstance(n, ast.Name) and n.id == x.id
                                                  for tg in st.targets for n in ast.walk(tg)):
                return "assigned from %s" % ast.unparse(st.value)[:80]
            if isinstance(st, (ast.With, ast.AsyncWith)) and any(
                    it.optional_vars is not None and getattr(it.optional_vars, "id", "") == x.id for it in st.items):
                return "a with target"
        return "not bound in the function (a closure, a global or a comprehension name)"

    # -- triggers -------------------------------------------------------------

    def _read_triggers(self, sql_dir):
        """{table: [(trigger, timing, {event: None | set(columns)}, function)]}
        of the migrations (numbered files, in order; rollback files are not
        applied); the last CREATE of a trigger or a function wins, a DROP TRIGGER
        with no later CREATE removes it. self.trigger_fns: function -> body."""
        files = sorted((f for f in os.listdir(sql_dir) if f.endswith(".sql") and re.match(r"\d+_", f)),
                       key=lambda f: (int(f.split("_", 1)[0]), f))
        live, self.trigger_fns = {}, {}
        for fn in files:
            with open(os.path.join(sql_dir, fn), encoding="utf-8", errors="replace") as fh:
                body = re.sub(r"--[^\n]*", " ", fh.read())
            evs = []
            for m in RX_FUNCTION.finditer(body):
                evs.append((m.start(), "fn", m))
            for m in RX_TRIGGER.finditer(body):
                evs.append((m.start(), "create", m))
            for m in RX_DROP_TRIGGER.finditer(body):
                evs.append((m.start(), "drop", m))
            for _p, kind, m in sorted(evs, key=lambda e: e[0]):
                if kind == "fn":
                    self.trigger_fns[m.group(1).lower()] = m.group(5)
                elif kind == "drop":
                    live.pop((m.group(1).lower(), m.group(2).lower()), None)
                else:
                    events = {}
                    for part in re.split(r"\s+OR\s+", _norm(m.group(3)), flags=re.I):
                        pm = re.fullmatch(r"(INSERT|UPDATE|DELETE|TRUNCATE)(?: OF (.*))?", part.strip(), re.I)
                        if pm:
                            cols = {c.strip().strip('"').lower() for c in pm.group(2).split(",")} if pm.group(2) \
                                else None
                            events[pm.group(1).upper()] = cols
                    live[(m.group(1).lower(), m.group(4).lower())] = (m.group(2).upper(), events,
                                                                      m.group(6).lower(), fn)
        out = defaultdict(list)
        for (trg, table), (timing, events, func, fn) in sorted(live.items()):
            out[table].append((trg, timing, events, func))
        for table in out:                        # BEFORE first, then by name (PostgreSQL's order)
            out[table].sort(key=lambda t: (t[1] != "BEFORE", t[0]))
        return dict(out)

    def _writes_of_sql(self, s):
        """[(table, event, columns | None)] a statement writes, in its text's order."""
        out = []
        for m in RX_INSERT.finditer(s):
            for t in self.tables(m.group(1)):
                out.append((m.start(), t, "INSERT", None))
        for m in RX_DO_UPDATE.finditer(s):
            cols = {c.split("=")[0].strip().strip('"').lower() for c in m.group(2).split(",") if "=" in c}
            for t in self.tables(m.group(1)):
                out.append((m.start(), t, "UPDATE", cols or None))
        for m in RX_UPDATE.finditer(s):
            cols = {c.split("=")[0].strip().strip('"').lower() for c in m.group(2).split(",") if "=" in c}
            for t in self.tables(m.group(1)):
                out.append((m.start(), t, "UPDATE", cols or None))
        for m in RX_DELETE.finditer(s):
            for t in self.tables(m.group(1)):
                out.append((m.start(), t, "DELETE", None))
        out.sort(key=lambda e: e[0])
        return [(t, ev, cols) for _p, t, ev, cols in out]

    def fired(self, writes, _active=()):
        """[(table, mode, blocking)] of the statements in the trigger functions
        the writes fire (a trigger's own writes fire theirs; a function already
        firing fires nothing again). A dynamic body is listed in self.unread."""
        out, done = [], set()
        for table, event, cols in writes:
            for trg, _timing, events, func in self.triggers.get(table, ()):
                if event not in events or (trg, table) in done or func in _active:
                    continue
                want = events[event]
                if event == "UPDATE" and want is not None and cols is not None and not (want & cols):
                    continue
                done.add((trg, table))
                body = self.trigger_fns.get(func)
                if body is None:
                    self.unread.add("trigger %s ON %s | %s(): no definition read" % (trg, table, func))
                    continue
                if RX_DYNAMIC.search(body):
                    self.unread.add("trigger %s ON %s | %s(): EXECUTE" % (trg, table, func))
                out.extend(self.locks_of_sql(body, _active + (func,)))
        return out

    # -- constants and texts ------------------------------------------------

    def _const(self, name, v):
        if isinstance(v, ast.Dict):
            vals = [self.text(x, {}) for x in v.values]
            if vals and all(t is not None for t in vals):
                self.dictvals[name] = vals
            for k, x in zip(v.keys, v.values):
                if isinstance(x, ast.Constant) and isinstance(x.value, str) and isinstance(k, ast.Constant):
                    self.dicts[str(k.value)].add(x.value)
                if isinstance(x, ast.Dict):
                    for k2, x2 in zip(x.keys, x.values):
                        if isinstance(k2, ast.Constant) and isinstance(x2, ast.Constant) and isinstance(x2.value, str):
                            self.dicts[str(k2.value)].add(x2.value)
            return
        if isinstance(v, (ast.Tuple, ast.List, ast.Set, ast.ListComp, ast.GeneratorExp, ast.SetComp)) \
                or isinstance(v, ast.BinOp) and isinstance(v.op, ast.BitOr) \
                or isinstance(v, ast.Call) and getattr(v.func, "id", "") in ("frozenset", "set", "tuple", "list",
                                                                            "sorted"):
            vals = self._choices(v, {})
            if vals is not None:
                self.listvals[name] = vals
            return
        s = self.text(v, {})
        if s is not None:
            self.consts[name] = s

    def text(self, x, local, plain=False):
        """An expression's text, or None. A part it cannot read is a
        placeholder: '{?t:a|b}' (these values), '{?d:k}' (a dictionary's
        values at key k) or '{?}'."""
        if isinstance(x, ast.Constant) and isinstance(x.value, str):
            return x.value
        if isinstance(x, ast.Name):
            if x.id in local:
                return local[x.id]
            v = self.consts.get(x.id)
            if v is None and MODULES:
                v = self._imported_value(x.id, "consts")
            return v
        if isinstance(x, ast.Subscript) and isinstance(x.slice, ast.Constant) and isinstance(x.slice.value, str):
            return "{?d:%s}" % x.slice.value
        if isinstance(x, ast.JoinedStr):
            out = []
            for v in x.values:
                if isinstance(v, ast.Constant):
                    out.append(str(v.value))
                elif isinstance(v, ast.FormattedValue):
                    t = self.text(v.value, local)
                    out.append(t if t is not None else "{?}")
            return "".join(out)
        if isinstance(x, ast.BinOp) and isinstance(x.op, ast.Add):
            a, b = self.text(x.left, local), self.text(x.right, local)
            if a is None and b is None:
                return None
            return (a if a is not None else "{?}") + (b if b is not None else "{?}")
        if isinstance(x, ast.BinOp) and isinstance(x.op, ast.Mod):
            a = self.text(x.left, local)
            return None if a is None else re.sub(r"%(?:\(\w+\))?s", "{?}", a)
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr in ("format", "strip"):
            a = self.text(x.func.value, local)
            return None if a is None else re.sub(r"\{\w*\}", "{?}", a)
        if isinstance(x, ast.Call) and getattr(x.func, "id", "") == "text" and x.args:
            return self.text(x.args[0], local)
        if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id not in local:
            if MODULES:
                mod = self._alias_mod(x.value.id, self._fn_stack[-1] if self._fn_stack else None)
                if mod in self.trees:
                    return self._space(mod)["consts"].get(x.attr)
                if mod is not None:
                    return self._module_consts(mod).get(x.attr)
            return self._module_consts(x.value.id).get(x.attr)
        if isinstance(x, ast.Subscript) and isinstance(x.value, ast.Name) and x.value.id in self.dictvals:
            return " ;; ".join(self.dictvals[x.value.id])
        if MODULES and isinstance(x, ast.Subscript) and isinstance(x.value, ast.Name) \
                and self._imported_value(x.value.id, "dictvals"):
            return " ;; ".join(self._imported_value(x.value.id, "dictvals"))
        if MODULES and isinstance(x, ast.Call) and isinstance(x.func, ast.Name):
            if self._fn_stack:
                q = self.resolve(self._fn_stack[-1], x.func.id)
            else:                               # a module-level constant: that module's defs and imports
                q = self.resolve(qn(self._cur, "<module>"), x.func.id)
            if q is not None:
                return self._returned_text(x, local, q)
        elif isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in self.defs:
            q = self.resolve(self._fn_stack[-1], x.func.id) if self._fn_stack else x.func.id
            if q is not None:
                return self._returned_text(x, local, q)
        if MODULES and isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute):
            q = self._attr_target(x.func, self._fn_stack[-1] if self._fn_stack else qn(self._cur, "<module>"))
            if q is not None:
                return self._returned_text(x, local, q)
        if not plain and (isinstance(x, (ast.BoolOp, ast.ListComp, ast.GeneratorExp, ast.SetComp)) or (
                isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "get")):
            vals = self._choices(x, local)
            return None if vals is None else self._alternatives(vals)
        if isinstance(x, ast.IfExp):
            for one, other in ((x.body, x.orelse), (x.orelse, x.body)):
                if isinstance(one, ast.Constant) and one.value is None:
                    return self.text(other, local)
            a, b = self.text(x.body, local), self.text(x.orelse, local)
            if a is None or b is None:
                return None
            if a == b:
                return a
            names = set()
            for v in (a, b):
                m = re.fullmatch(r"\{\?t:([^}]*)\}", v)
                names.update(m.group(1).split("|") if m else [v])
            if all(re.fullmatch(_W, n) for n in names):
                return "{?t:%s}" % "|".join(sorted(names))
            return a + " ;; " + b
        return None

    @staticmethod
    def _alternatives(texts):
        """Several texts as one: '{?t:a|b}' when all are names, else joined by ' ;; '."""
        flat = set()
        for t in texts:
            m = re.fullmatch(r"\{\?t:([^}]*)\}", t)
            flat.update(m.group(1).split("|") if m else [t])
        uniq = sorted(flat)
        if all(re.fullmatch(_W, t) for t in uniq):
            return "{?t:%s}" % "|".join(uniq)
        return " ;; ".join(sorted(set(texts)))

    def _choices(self, x, local):
        """The texts a value can take, or None when one part cannot be read."""
        if isinstance(x, ast.Constant):
            if x.value is None:
                return []                       # None is never a statement's text
            return [x.value] if isinstance(x.value, str) else None
        if isinstance(x, ast.Name):
            if x.id in local:
                m = re.fullmatch(r"\{\?t:([^}]*)\}", local[x.id])
                return m.group(1).split("|") if m else [local[x.id]]
            if x.id in self.listvals:
                return list(self.listvals[x.id])
            if x.id in self.dictvals:
                return list(self.dictvals[x.id])
            if x.id not in self.consts and MODULES:
                for kind in ("listvals", "dictvals"):
                    v = self._imported_value(x.id, kind)
                    if v is not None:
                        return list(v)
                v = self._imported_value(x.id, "consts")
                return None if v is None else [v]
            return [self.consts[x.id]] if x.id in self.consts else None
        if isinstance(x, (ast.Tuple, ast.List, ast.Set)):
            out = []
            for e in x.elts:
                c = self._choices(e, local)
                if c is None:
                    return None
                out.extend(c)
            return out
        if isinstance(x, ast.BinOp) and isinstance(x.op, ast.BitOr):
            a, b = self._choices(x.left, local), self._choices(x.right, local)
            return None if a is None or b is None else a + b
        if isinstance(x, ast.BoolOp) and isinstance(x.op, ast.Or) or isinstance(x, ast.IfExp):
            parts = x.values if isinstance(x, ast.BoolOp) else [x.body, x.orelse]
            out = []
            for e in parts:
                c = self._choices(e, local)
                if c is None:
                    return None
                out.extend(c)
            return out
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in (
                "frozenset", "set", "tuple", "list", "sorted") and len(x.args) == 1:
            return self._choices(x.args[0], local)
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and isinstance(x.func.value, ast.Name) \
                and x.func.value.id in self.dictvals and x.func.attr in ("values", "get"):
            out = list(self.dictvals[x.func.value.id])
            if x.func.attr == "get" and len(x.args) == 2:
                d = self._choices(x.args[1], local)
                if d is None:
                    return None
                out.extend(d)
            return out
        if isinstance(x, (ast.ListComp, ast.GeneratorExp, ast.SetComp)) and len(x.generators) == 1:
            g = x.generators[0]
            if isinstance(g.target, ast.Name) and isinstance(x.elt, ast.Name) and x.elt.id == g.target.id:
                return self._choices(g.iter, local)
        t = self.text(x, local, plain=True)
        return None if t is None else [t]

    def _module_consts(self, mod):
        """Another api module's string constants, read in its own order."""
        if mod not in self._modules:
            self._modules[mod] = {}
            path = os.path.join(self.api, mod + ".py")
            if re.fullmatch(_W, mod) and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                loc = {}
                for node in tree.body:
                    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                        t = self.text(node.value, loc)
                        if t is not None:
                            loc[node.targets[0].id] = t
                self._modules[mod] = loc
        return self._modules[mod]

    def _returned_text(self, call, local, q=None):
        """The text a helper returns (its returns joined by ' ;; '), its
        parameters bound to the call's readable arguments; None if none reads."""
        name = q or call.func.id
        if name in self._ret_active:
            return None
        fn = self.qdefs.get(name) or self.defs[name]
        names = [a.arg for a in fn.args.posonlyargs + fn.args.args]
        loc = {} if name in self.top else dict(local)      # a nested helper reads its caller's names
        for n, v in zip(names, call.args):
            t = self.text(v, local)
            if t is not None:
                loc[n] = t
        for k in call.keywords:
            if k.arg:
                t = self.text(k.value, local)
                if t is not None:
                    loc[k.arg] = t
        self._ret_active.add(name)
        prev = self._cur
        if MODULES:                             # the helper's names: its scope, its module's constants
            self._fn_stack.append(name)
            self._cur = mod_of(name)
        try:
            rets = []

            def visit(stmts):
                for st in stmts:
                    if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                        t = self.text(st.value, loc)
                        if t is not None:
                            loc[st.targets[0].id] = t
                    elif isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name) \
                            and isinstance(st.op, ast.Add):
                        t = self.text(st.value, loc)
                        if t is not None:
                            loc[st.target.id] = loc.get(st.target.id, "") + t
                    elif isinstance(st, ast.Return) and st.value is not None:
                        t = self.text(st.value, loc)
                        if t is not None:
                            rets.append(t)
                    for field in ("body", "orelse", "finalbody"):
                        sub = getattr(st, field, None)
                        if isinstance(sub, list) and not isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                                             ast.ClassDef)):
                            visit(sub)
                    for h in getattr(st, "handlers", []) or []:
                        visit(h.body)
            visit(fn.body)
        finally:
            self._ret_active.discard(name)
            if MODULES:
                self._fn_stack.pop()
                self._cur = prev
        return " ;; ".join(dict.fromkeys(rets)) if rets else None

    def tables(self, tok):
        """A table token's names: placeholders expanded, '?' when one cannot be."""
        parts = re.split("(" + _PH + ")", tok)
        choices = []
        for p in parts:
            if not p:
                continue
            if p.startswith("{?t:"):
                choices.append(p[4:-1].split("|"))
            elif p.startswith("{?d:"):
                vals = sorted(self.dicts.get(p[4:-1], ()))
                if not vals:
                    return ["?"]
                choices.append(vals)
            elif p.startswith("{?"):
                return ["?"]
            else:
                choices.append([p])
        names = sorted({"".join(c).lower() for c in itertools.product(*choices)})
        return [n for n in names if re.fullmatch(_W, n)] or ["?"]

    def _param_values(self):
        """fn -> param -> '{?t:a|b}' for a parameter every call site gives a
        readable string (a literal, a constant, a dictionary's values at a key,
        or the caller's own such parameter); read to a fixed point."""
        sites = []
        for caller in ast.walk(self.tree):
            if isinstance(caller, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for c in ast.walk(caller):
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in self.defs:
                        sites.append((caller.name, c))
        vals = defaultdict(dict)
        for _round in range(5):
            got = defaultdict(lambda: defaultdict(set))
            texts = defaultdict(lambda: defaultdict(set))
            bad = defaultdict(set)
            for caller, c in sites:
                callee = self.defs[c.func.id]
                names = [a.arg for a in callee.args.posonlyargs + callee.args.args]
                pairs = [(n, v) for n, v in zip(names, c.args) if not isinstance(v, ast.Starred)]
                pairs += [(k.arg, k.value) for k in c.keywords if k.arg]
                for n, v in pairs:
                    t = self.text(v, vals.get(caller, {}))
                    if t is None:
                        bad[c.func.id].add(n)
                        continue
                    if "{?}" not in t and re.fullmatch(r"(?:[A-Za-z0-9_]|" + _PH + r")+", t):
                        for piece in self.tables(t) if "{?" in t else [t]:
                            got[c.func.id][n].add(piece)
                    else:
                        texts[c.func.id][n].add(t)    # a statement's text, not a name
            new = defaultdict(dict)
            for fn in set(got) | set(texts):
                for n in set(got[fn]) | set(texts[fn]):
                    if n in bad[fn]:
                        continue
                    ids, txs = got[fn][n], texts[fn][n]
                    if txs:
                        alts = sorted(txs | ids)
                        if len(alts) <= 40:
                            new[fn][n] = " ;; ".join(alts)
                    elif "?" not in ids and len(ids) <= 40:
                        new[fn][n] = "{?t:%s}" % "|".join(sorted(ids))
            if new == vals:
                break
            vals = new
        return vals

    def _param_values_q(self):
        """_param_values over every read module, keyed by the qualified name:
        a call site's callee is the def resolve or _attr_target gives it, and
        its arguments are read in the caller's scope and module."""
        sites = []
        for m, tree in self.trees.items():
            qmap = {id(node): q for q, node in self._all_fns() if mod_of(q) == m}
            for fnode in ast.walk(tree):
                if not isinstance(fnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                caller = qmap.get(id(fnode)) or qn(m, "<method>" + fnode.name)
                for c in _own_nodes(fnode):
                    if not isinstance(c, ast.Call):
                        continue
                    if isinstance(c.func, ast.Name):
                        q = self.resolve(caller, c.func.id)
                    else:
                        q = self._attr_target(c.func, caller)
                    if q is not None:
                        sites.append((caller, c, q))
        vals = defaultdict(dict)
        for _round in range(5):
            got = defaultdict(lambda: defaultdict(set))
            texts = defaultdict(lambda: defaultdict(set))
            bad = defaultdict(set)
            for caller, c, q in sites:
                callee = self.qdefs.get(q) or self.defs[q]
                names = [a.arg for a in callee.args.posonlyargs + callee.args.args]
                pairs = [(n, v) for n, v in zip(names, c.args) if not isinstance(v, ast.Starred)]
                pairs += [(k.arg, k.value) for k in c.keywords if k.arg]
                self._fn_stack.append(caller)
                self._cur = mod_of(caller)
                try:
                    for n, v in pairs:
                        t = self.text(v, vals.get(caller, {}))
                        if t is None:
                            bad[q].add(n)
                            continue
                        if "{?}" not in t and re.fullmatch(r"(?:[A-Za-z0-9_]|" + _PH + r")+", t):
                            for piece in self.tables(t) if "{?" in t else [t]:
                                got[q][n].add(piece)
                        else:
                            texts[q][n].add(t)
                finally:
                    self._fn_stack.pop()
                    self._cur = "main"
            new = defaultdict(dict)
            for fn in set(got) | set(texts):
                for n in set(got[fn]) | set(texts[fn]):
                    if n in bad[fn]:
                        continue
                    ids, txs = got[fn][n], texts[fn][n]
                    if txs:
                        alts = sorted(txs | ids)
                        if len(alts) <= 40:
                            new[fn][n] = " ;; ".join(alts)
                    elif "?" not in ids and len(ids) <= 40:
                        new[fn][n] = "{?t:%s}" % "|".join(sorted(ids))
            if new == vals:
                break
            vals = new
        return vals

    # -- one statement's locks ----------------------------------------------

    @staticmethod
    def _depths(s):
        """The parenthesis depth at every position of `s` (a '(' itself is at the
        outer depth; parentheses inside '...' do not count)."""
        out, d, quoted = [], 0, False
        for ch in s:
            if ch == "'":
                quoted = not quoted
            if not quoted and ch == ")":
                d = max(0, d - 1)
            out.append(d)
            if not quoted and ch == "(":
                d += 1
        return out

    def locks_of_sql(self, sql, _active=()):
        """[(table, mode, blocking)] a statement takes, in its text's order, then
        (TRIGGERS) what the triggers its writes fire take."""
        s = _norm(sql)
        out = []
        for m in RX_KEY.finditer(s):
            out.append((m.start(), key_name(_balanced(m.group(2))), "KEY", m.group(1) is None))
        for m in RX_UPDATE.finditer(s):
            cols = {c.split("=")[0].strip().strip('"').lower() for c in m.group(2).split(",") if "=" in c}
            for t in self.tables(m.group(1)):
                mode = UPD if cols & KEY_COLUMNS.get(t, frozenset({"id"})) else NKU
                out.append((m.start(), t, mode, True))
                for parent in self._set_parents(t, m.group(2)):     # FK_COLUMNS: a foreign key set: checked
                    out.append((m.start(), parent, KS, True))
        for m in RX_DELETE.finditer(s):
            for t in self.tables(m.group(1)):
                out.append((m.start(), t, UPD, True))
        ups = {m.start() for m in RX_UPSERT.finditer(s)}
        waits = {m.start() for m in RX_ON_CONFLICT.finditer(s)} if INSERT_WAITS else set()
        for m in RX_INSERT.finditer(s):
            named = self._insert_cols(s, m.end()) if FK_COLUMNS else None
            for t in self.tables(m.group(1)):
                if INSERT_WAITS:                # its own key: held; with ON CONFLICT, first waited for
                    out.append((m.start(), t, INS, True if m.start() in waits else HELD))
                if m.start() in ups:
                    out.append((m.start(), t, NKU, True))
                for parent in self._insert_parents(t, named):
                    out.append((m.start(), parent, KS, True))
        if FK_COLUMNS:                          # an upsert's DO UPDATE SET of a foreign key
            for m in RX_DO_UPDATE.finditer(s):
                for t in self.tables(m.group(1)):
                    for parent in self._set_parents(t, m.group(2)):
                        out.append((m.start(), parent, KS, True))
        depth = self._depths(s) if FOR_DEPTH else None
        for m in RX_FOR.finditer(s):
            mode, blocking = m.group(1).upper(), m.group(3) is None
            lo = 0
            if FOR_DEPTH:                       # the FOR clause's own query: its depth, its group
                d = depth[m.start()]
                lo = next((j + 1 for j in range(m.start() - 1, -1, -1) if s[j] == "(" and depth[j] == d - 1), 0) \
                    if d else 0
            if m.group(2):
                alias = {}
                if FOR_DEPTH:
                    for a in RX_ALIAS.finditer(s, lo, m.start()):
                        if depth[a.start()] == d:
                            alias.setdefault(a.group(2).lower(), self.tables(a.group(1)))
                for a in RX_ALIAS.finditer(s, 0, m.start()):
                    alias.setdefault(a.group(2).lower(), self.tables(a.group(1)))
                ts = []
                for t in m.group(2).split(","):
                    t = t.strip().lower()
                    ts.extend(alias.get(t, [t]))
            elif FOR_DEPTH:
                sels = [x.start() for x in RX_SELECT.finditer(s, lo, m.start()) if depth[x.start()] == d]
                ts = []
                for f in RX_FROM.finditer(s, sels[-1] if sels else lo, m.start()):
                    if depth[f.start()] == d:
                        ts.extend(self.tables(f.group(1)))
            else:
                sels = [x.start() for x in RX_SELECT.finditer(s, 0, m.start())]
                ts = []
                for f in RX_FROM.finditer(s, sels[-1] if sels else 0, m.start()):
                    ts.extend(self.tables(f.group(1)))
            for t in ts:
                out.append((m.start(), t, mode, blocking))
        out.sort(key=lambda e: e[0])
        own = [(t, mode, b) for _p, t, mode, b in out]
        if TRIGGERS:
            own += self.fired(self._writes_of_sql(s), _active)
        return own

    # -- entries -------------------------------------------------------------

    def _opens_session(self, fn):
        todo = list(ast.iter_child_nodes(fn))
        own = []
        while todo:                             # its own body: not a nested def's, class's or lambda's
            n = todo.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            own.append(n)
            todo.extend(ast.iter_child_nodes(n))
        for sub in own:
            if isinstance(sub, (ast.AsyncWith, ast.With)):
                for it in sub.items:
                    c = it.context_expr
                    if isinstance(c, ast.Call) and getattr(c.func, "id", "") in OPENERS:
                        return True
                    if MODULES and isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) \
                            and c.func.attr in OPENERS:    # database.async_session()
                        return True
        return False

    def _roots(self):
        roots = {}
        for node in self.tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_METHODS \
                        and getattr(d.func.value, "id", "") == "app":
                    roots[node.name] = "route"
            if node.name not in roots and self._opens_session(node):
                roots[node.name] = "session"
        for m, tree in self.trees.items():      # another module: routes of its APIRouter objects
            if m == "main":
                continue
            routers = {n.targets[0].id for n in tree.body
                       if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                       and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") == "APIRouter"}
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                q = qn(m, node.name)
                for d in node.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) \
                            and d.func.attr in ROUTE_METHODS and getattr(d.func.value, "id", "") in routers:
                        roots[q] = "route"
                if q not in roots and self._opens_session(node):
                    roots[q] = "session"
        for q, node in self.qdefs.items():
            if self._opens_session(node):
                roots[q] = "session"
        return roots

    # -- flattening ----------------------------------------------------------

    def events(self, name):
        """The function's lock events in source order, callees inlined:
        ('L', table, mode, blocking, place) | ('HOIST', [(table, mode, blocking)]);
        place = (function, statement head, occurrence)."""
        if name in self._memo:
            return self._memo[name]
        self._memo[name] = []                   # a cycle inlines nothing
        params = self.params.get(name, {}) if MODULES else self.params.get(name.rsplit(".", 1)[-1], {})
        ctx = {"seen": defaultdict(int), "local": dict(params), "fn": name,
               "players_vars": set(), "modvars": {}}
        if ORM_TYPES:                           # rule 1: a parameter annotated Player
            ctx["players_vars"].update(self._player_params(self.qdefs.get(name) or self.defs[name]))
        self._fn_stack.append(name)
        prev, self._cur = self._cur, mod_of(name)
        try:
            out = self._body((self.qdefs.get(name) or self.defs[name]).body, ctx)
        finally:
            self._fn_stack.pop()
            self._cur = prev
        self._memo[name] = out
        return out

    def resolve(self, caller, name):
        """The def a bare-name call in `caller` (qualified) reaches: a def nested
        in the caller or in a function enclosing it, else a module-level def of
        its module, else (MODULES) the def an import in its scope names."""
        m = mod_of(caller)
        pre = "" if m == "main" else m + ":"
        parts = (caller.split(":", 1)[1] if ":" in caller else caller).split(".")
        for i in range(len(parts), 0, -1):
            q = pre + ".".join(parts[:i]) + "." + name
            if q in self.qdefs:
                return q
        if pre + name in self.top:
            return pre + name
        if MODULES:
            t = self._imported(name, caller)
            if t and t[0] == "name" and t[1] in self.trees and qn(t[1], t[2]) in self.top:
                return qn(t[1], t[2])
        return None

    def _place(self, ctx, head):
        k = ctx["seen"][head]
        ctx["seen"][head] += 1
        return (ctx["fn"], head, k)

    def _body(self, stmts, ctx):
        out = []
        for st in stmts:
            out.extend(self._stmt(st, ctx))
        return out

    def _stmt(self, st, ctx):
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return []
        if isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
            if isinstance(st, ast.While):
                head = self._calls(st.test, ctx)
            else:
                head = self._calls(st.iter, ctx)
                if ORM_TYPES:                   # rule 3: a loop over Players
                    self._player_track(st, ctx["players_vars"], ctx["fn"])
                if isinstance(st.target, ast.Name) and isinstance(st.iter, (ast.Tuple, ast.List)) and st.iter.elts \
                        and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in st.iter.elts):
                    ctx["local"][st.target.id] = "{?t:%s}" % "|".join(sorted(e.value for e in st.iter.elts))
                it = st.iter
                if isinstance(st.target, ast.Name) and not isinstance(it, (ast.Tuple, ast.List)):
                    vals = self._choices(it, ctx["local"])
                    if vals:
                        ctx["local"][st.target.id] = self._alternatives(vals)
                if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) and not it.args \
                        and isinstance(it.func.value, ast.Name) and it.func.value.id in self.dictvals:
                    vals = self._alternatives(self.dictvals[it.func.value.id])
                    if it.func.attr == "values" and isinstance(st.target, ast.Name):
                        ctx["local"][st.target.id] = vals
                    if it.func.attr == "items" and isinstance(st.target, ast.Tuple) and len(st.target.elts) == 2 \
                            and isinstance(st.target.elts[1], ast.Name):
                        ctx["local"][st.target.elts[1].id] = vals
                if isinstance(st.target, ast.Tuple) and isinstance(st.iter, (ast.Tuple, ast.List)) and st.iter.elts \
                        and all(isinstance(e, ast.Tuple) and len(e.elts) == len(st.target.elts) for e in st.iter.elts):
                    for i, tg in enumerate(st.target.elts):
                        vals = [e.elts[i] for e in st.iter.elts]
                        if isinstance(tg, ast.Name) and all(
                                isinstance(v, ast.Constant) and isinstance(v.value, str) and re.fullmatch(_W, v.value)
                                for v in vals):
                            ctx["local"][tg.id] = "{?t:%s}" % "|".join(sorted({v.value for v in vals}))
            body = self._body(st.body, ctx) + self._body(st.orelse, ctx)
            hoist = [e[1:4] for e in body if e[0] == "L"] + [x for e in body if e[0] == "HOIST" for x in e[1]]
            return head + ([("HOIST", hoist)] if hoist else []) + body
        if isinstance(st, ast.If):
            out = self._calls(st.test, ctx) + self._body(st.body, ctx) + self._body(st.orelse, ctx)
            t = st.test
            if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.NotIn) \
                    and isinstance(t.left, ast.Name) and st.body and isinstance(st.body[-1], ast.Raise):
                vals = self._choices(t.comparators[0], ctx["local"])
                if vals:
                    ctx["local"][t.left.id] = self._alternatives(vals)
            return out
        if isinstance(st, (ast.With, ast.AsyncWith)):
            out = []
            for it in st.items:
                out.extend(self._calls(it.context_expr, ctx))
            return out + self._body(st.body, ctx)
        if isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
            out = self._body(st.body, ctx)
            for h in st.handlers:
                out.extend(self._body(h.body, ctx))
            return out + self._body(st.orelse, ctx) + self._body(st.finalbody, ctx)
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            t = self.text(st.value, ctx["local"])
            if t is not None:
                prev = ctx["local"].get(st.targets[0].id)
                ctx["local"][st.targets[0].id] = t if prev is None or prev == t else prev + " ;; " + t
            if self._loads_player(st.value):
                ctx["players_vars"].add(st.targets[0].id)
            elif ORM_TYPES:                     # rules 2 and 4
                self._player_track(st, ctx["players_vars"], ctx["fn"])
            v = st.value
            if MODULES and isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and not v.args:
                mod = self.modfns.get(self.resolve(ctx["fn"], v.func.id))
                if mod is not None:             # mrw = _mrw_mod(): mrw is that module
                    ctx["modvars"][st.targets[0].id] = mod
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
            t = self.text(st.value, ctx["local"])
            if t is not None:
                ctx["local"][st.target.id] = t
            if self._loads_player(st.value):
                ctx["players_vars"].add(st.target.id)
            elif ORM_TYPES:
                self._player_track(st, ctx["players_vars"], ctx["fn"])
        if ORM_TYPES and isinstance(st, ast.Assign) and len(st.targets) == 1 \
                and isinstance(st.targets[0], ast.Tuple):     # rule 2: p, created = await helper(...)
            self._player_track(st, ctx["players_vars"], ctx["fn"])
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Tuple) \
                and isinstance(st.value, ast.Tuple) and len(st.value.elts) == len(st.targets[0].elts):
            for tg, v in zip(st.targets[0].elts, st.value.elts):
                if isinstance(tg, ast.Name):
                    t = self.text(v, ctx["local"])
                    if t is not None:
                        ctx["local"][tg.id] = t
        if isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name) and isinstance(st.op, ast.Add):
            t = self.text(st.value, ctx["local"])
            if t is not None:
                ctx["local"][st.target.id] = ctx["local"].get(st.target.id, "") + t
        return self._calls(st, ctx) + self._orm_store(st, ctx)

    @staticmethod
    def _loads_player(v):
        for sub in ast.walk(v):
            if isinstance(sub, ast.Call) and sub.args and getattr(sub.args[0], "id", "") == "Player":
                if getattr(sub.func, "id", "") == "select" or getattr(sub.func, "attr", "") == "get":
                    return True
        return False

    def _orm_store(self, st, ctx):
        tgts = st.targets if isinstance(st, ast.Assign) else (
            [st.target] if isinstance(st, (ast.AugAssign, ast.AnnAssign)) else [])
        out = []
        for t in tgts:
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in ctx["players_vars"]:
                mode = UPD if t.attr in KEY_COLUMNS["players"] else NKU
                place = self._place(ctx, "ORM %s.%s =" % (t.value.id, t.attr))
                out.append(("L", "players", mode, True, place))
                if FK_COLUMNS and not (isinstance(st.value, ast.Constant) and st.value.value is None):
                    col = self.model_cols.get("Player", {}).get(t.attr, t.attr.lower())
                    for parent in sorted(self._fk_map("players").get(col, ())):    # a foreign key set: checked
                        out.append(("L", parent, KS, True, place))
                if TRIGGERS:
                    for tb, md, b in self.fired([("players", "UPDATE", {t.attr.lower()})]):
                        out.append(("L", tb, md, b, place))
        return out

    def _calls(self, node, ctx):
        """Lock events of every call under `node`, in source order."""
        calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
        spawned = set()
        for c in calls:
            if getattr(c.func, "attr", getattr(c.func, "id", "")) in SPAWNERS:
                for a in c.args:
                    spawned.update(id(sub) for sub in ast.walk(a))
        calls.sort(key=lambda c: (c.lineno, c.col_offset))
        out = []
        for c in calls:
            if id(c) in spawned:
                continue
            fname = getattr(c.func, "id", None)
            attr = getattr(c.func, "attr", None)
            first = getattr(c.args[0], "id", "") if c.args else ""
            if fname == "text" and c.args:
                sql = self.text(c.args[0], ctx["local"])
                if sql is None:
                    self.unread.add("%s | text(%s)" % (ctx["fn"], ast.unparse(c.args[0])[:60]))
                    continue
                place = self._place(ctx, _norm(sql)[:72])
                for t, mode, b in self.locks_of_sql(sql):
                    out.append(("L", t, mode, b, place))
            elif fname in ("update", "delete") and first in self.models:
                place = self._place(ctx, "%s(%s)" % (fname, first))
                out.append(("L", self.models[first], UPD if fname == "delete" else NKU, True, place))
                if TRIGGERS:                    # its columns are not read: every UPDATE trigger fires
                    for tb, md, b in self.fired([(self.models[first], fname.upper(), None)]):
                        out.append(("L", tb, md, b, place))
            elif attr == "with_for_update":
                root = c.func.value
                while isinstance(root, ast.Call) and isinstance(root.func, ast.Attribute):
                    root = root.func.value
                rfirst = getattr(root.args[0], "id", "") if isinstance(root, ast.Call) and root.args else ""
                if isinstance(root, ast.Call) and getattr(root.func, "id", "") == "select" and rfirst in self.models:
                    kw = {k.arg: k.value for k in c.keywords}
                    on = lambda k: isinstance(kw.get(k), ast.Constant) and bool(kw[k].value)  # noqa: E731
                    mode = SH if on("read") else (NKU if on("key_share") else UPD)
                    place = self._place(ctx, "select(%s).with_for_update" % rfirst)
                    out.append(("L", self.models[rfirst], mode, not (on("skip_locked") or on("nowait")), place))
            elif attr == "get" and first in self.models and any(k.arg == "with_for_update" for k in c.keywords):
                place = self._place(ctx, "get(%s, with_for_update)" % first)
                out.append(("L", self.models[first], UPD, True, place))
            elif fname in self.models:
                place = self._place(ctx, "%s(...)" % fname)
                if INSERT_WAITS:                # an ORM insert: its own key, held
                    out.append(("L", self.models[fname], INS, HELD, place))
                named = None                    # FK_COLUMNS: the columns its keyword arguments set
                if FK_COLUMNS and not c.args and all(k.arg for k in c.keywords):
                    mcols = self.model_cols.get(fname, {})
                    named = {mcols.get(k.arg, k.arg.lower()) for k in c.keywords
                             if not (isinstance(k.value, ast.Constant) and k.value.value is None)}
                for parent in self._insert_parents(self.models[fname], named):
                    out.append(("L", parent, KS, True, place))
                if TRIGGERS:
                    for tb, md, b in self.fired([(self.models[fname], "INSERT", None)]):
                        out.append(("L", tb, md, b, place))
            elif fname is not None and self.resolve(ctx["fn"], fname) is not None:
                q = self.resolve(ctx["fn"], fname)
                if self.roots.get(q) == "session" or (q == fname and self.roots.get(fname) == "session"):
                    continue                    # its own session: another transaction
                out.extend(self.events(q))
            elif MODULES and attr is not None and self._attr_target(c.func, ctx["fn"], ctx["modvars"]) is not None:
                q = self._attr_target(c.func, ctx["fn"], ctx["modvars"])
                if self.roots.get(q) == "session":
                    continue
                out.extend(self.events(q))
        return out


def walk(events):
    """One pass: (the held list, [(index, event, held length)] for every
    blocking players lock, the first index of a blocking lock per table, the
    identity keys taken [(index, event)]). A HOIST's locks count as held."""
    held, players, first, keys = [], [], {}, []
    for i, e in enumerate(events):
        if e[0] == "HOIST":
            held.extend((t, m) for (t, m, b) in e[1] if b)
            continue
        if not e[3]:
            continue
        if e[3] == HELD:                        # held from here on, never a wait
            first.setdefault(e[1], i)
            held.append((e[1], e[2]))
            continue
        if e[1] == "players":
            players.append((i, e, len(held)))
        if e[2] == "KEY" and e[1] in IDENTITY_KEYS:
            keys.append((i, e))
        first.setdefault(e[1], i)
        held.append((e[1], e[2]))
    return held, players, first, keys


def _deletion_wait(e):
    """The deletion's event as a wait (table, mode), or None when it is no wait."""
    fn, head = e[4][0], e[4][1]
    if not e[3] or e[3] == HELD:
        return None
    if e[1] == "players":
        if fn in GUARDED_FNS:
            return None
        if fn in OWN_ROW_FNS:
            return ("players", OWN_UP) if e[2] == UPD else None
    if e[1] in IDENTITY_KEYS and fn in OWN_KEY_FNS:
        return None
    return (e[1], e[2])


def step1(src):
    """{'A': {(table, mode)}, 'B': {(table, mode)}}: the deletion's blocking waits
    after its own players row is held FOR NO KEY UPDATE (A) and FOR UPDATE (B)."""
    ev = [e for e in src.events(DELETION) if e[0] == "L"]
    a_at = next(i for i, e in enumerate(ev) if e[4][0] == DELETION and e[4][1].startswith(PHASE_A_MARK))
    b_at = next(i for i, e in enumerate(ev) if e[4][0] == DELETION and e[4][1] == PHASE_B_HEAD)
    out = {}
    for ph, at in (("A", a_at), ("B", b_at)):
        out[ph] = {w for w in (_deletion_wait(e) for e in ev[at + 1:]) if w is not None}
    # From the tombstone's flush on it holds its row FOR UPDATE: a later store
    # of a key column (discord_id) waits for nothing.
    out["B"].discard(("players", OWN_UP))
    return out


# The deletion's own row: in phase A it holds NO KEY UPDATE (a route's KEY SHARE
# does not wait for it); in phase B it holds UPDATE (every lock waits).
HELD_BY_DELETION = {"A": NKU, "B": UPD}


def census(src=None, entries=None):
    """(step 1, rows): rows = {(place, phase, held tables): {"entries": [...],
    "class": CLEAR|KEY|UPGRADE|READ, "fallback": the class without the
    identity key, "key": the identity key's place, for KEY}}."""
    src = src or Source()
    s1 = step1(src)
    rows = defaultdict(lambda: {"entries": set(), "keys": set(), "nokey": False, "beyond_upgrade": False})
    for entry in sorted(src.roots if entries is None else entries):
        if entry == DELETION:
            continue
        held, players, first, keys = walk(src.events(entry))
        for i, e, n in players:
            for phase in ("A", "B"):
                if not conflicts(HELD_BY_DELETION[phase], e[2]):
                    continue
                hit = sorted({t for (t, m) in held[:n]
                              if any((t == dt or "?" in (t, dt)) and conflicts(m, dm) for (dt, dm) in s1[phase])})
                r = rows[(e[4], phase, tuple(hit))]
                r["entries"].add(entry)
                if hit and any(dm != OWN_UP for (t, m) in held[:n] for (dt, dm) in s1[phase]
                               if (t == dt or "?" in (t, dt)) and conflicts(m, dm)):
                    r["beyond_upgrade"] = True
                if hit:
                    bound = min([i] + [first[t] for t in hit if t in first])
                    k = next((ke for ki, ke in keys if ki < bound), None)
                    if k is None:
                        r["nokey"] = True
                    else:
                        r["keys"].add(k[4])
    out = {}
    for (place, phase, hit), r in rows.items():
        # the class without the identity key: a KEY row's is UPGRADE or READ (docstring, 3.)
        fallback = "CLEAR" if not hit else "UPGRADE" if not r["beyond_upgrade"] else "READ"
        cls = "KEY" if hit and not r["nokey"] and len(r["keys"]) == 1 else fallback
        out[(place, phase, hit)] = {"entries": sorted(r["entries"]), "class": cls, "fallback": fallback,
                                    "key": sorted(r["keys"])[0] if cls == "KEY" else None}
    return s1, out


RANK = {"CLEAR": 0, "KEY": 1, "UPGRADE": 2, "READ": 3}


def site_key(place):
    return "%s | %s | %d" % place


def sites(src=None, entries=None):
    """The census keyed by statement site: {site: {"class": the highest of its
    rows (READ > UPGRADE > KEY > CLEAR), "fallback": the highest of its rows'
    fallbacks (the site's class were no identity key read), "phases": the
    phases where it holds something, "held": the tables it can hold there,
    "entries": every entry that reaches it, "keys": the identity keys' places
    of its KEY rows}}."""
    s1, rows = census(src, entries)
    out = {}
    for (place, phase, hit), r in rows.items():
        d = out.setdefault(site_key(place), {"class": "CLEAR", "fallback": "CLEAR", "phases": set(),
                                              "held": set(), "entries": set(), "keys": set()})
        if RANK[r["class"]] > RANK[d["class"]]:
            d["class"] = r["class"]
        if RANK[r["fallback"]] > RANK[d["fallback"]]:
            d["fallback"] = r["fallback"]
        d["entries"].update(r["entries"])
        if hit:
            d["phases"].add(phase)
            d["held"].update(hit)
        if r["key"] is not None:
            d["keys"].add(site_key(r["key"]))
    for d in out.values():
        for k in ("phases", "held", "entries", "keys"):
            d[k] = sorted(d[k])
    return s1, out


FROZEN = os.path.join(HERE, "mdpl_census_frozen.json")
COMPARED = ("class", "fallback", "phases", "held", "entries", "keys")
# The census as first frozen, before the six switches (the regression control's file), and what it records.
BASE = os.path.join(HERE, "mdpl_census_base.json")
BASE_FIELDS = ("class", "phases", "held", "entries", "keys")
SWITCHES = ("MODULES", "TRIGGERS", "INSERT_WAITS", "FOR_DEPTH", "FK_COLUMNS", "ORM_TYPES")


def measured(src=None):
    """What test_mdpl_census compares with the frozen file: step 1, every
    site's computed fields, the unread statements and (ORM_TYPES) the
    untyped Player-column stores."""
    src = src or Source()
    s1, got = sites(src)
    out = {"step1": {ph: sorted("%s / %s" % w for w in s1[ph]) for ph in ("A", "B")},
            "sites": {k: {f: d[f] for f in COMPARED} for k, d in got.items()},
            "unread": sorted(src.unread)}
    if ORM_TYPES:                               # the Player-column stores on objects not known to be Players
        out["untyped"] = sorted(src.untyped)
    return out


def freeze(old, m=None):
    """The frozen document for measure `m`, keeping `old`'s judgements."""
    m = m or measured()
    doc = {k: old[k] for k in ("about", "bound_iii", "classes", "scenes") if k in old}
    doc["step1"] = m["step1"]
    doc["sites"] = {}
    for k, d in m["sites"].items():
        d = dict(d)
        was = old.get("sites", {}).get(k, {})
        for f in ("covers", "judged", "why"):   # kept on every site, whatever its class
            if f in was:
                d[f] = was[f]
        if d["class"] == "READ":
            d["why"] = was.get("why", "")
        doc["sites"][k] = d
    doc["unread"] = {u: old.get("unread", {}).get(u, "") for u in m["unread"]}
    if "untyped" in m:                          # a reason per untyped store, "" when new
        doc["untyped"] = {u: old.get("untyped", {}).get(u, "") for u in m["untyped"]}
    return doc


if __name__ == "__main__":
    sys.setrecursionlimit(20000)
    if "--freeze" in sys.argv:
        old = {}
        if os.path.exists(FROZEN):
            with open(FROZEN, encoding="utf-8") as fh:
                old = json.load(fh)
        doc = freeze(old)
        with open(FROZEN, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
            fh.write("\n")
        cls, eff = defaultdict(int), defaultdict(int)
        for d in doc["sites"].values():
            cls[d["class"]] += 1
            eff[d.get("judged", d["class"])] += 1
        print("FROZEN sites", len(doc["sites"]), dict(sorted(cls.items())), "unread", len(doc["unread"]))
        print("JUDGED (a judged site counted at its judgement)", dict(sorted(eff.items())))
        for k, d in sorted(doc["sites"].items()):
            if d["class"] == "READ" and not d["why"]:
                print("NO JUDGEMENT", k)
            if d["fallback"] != d["class"] and not d.get("covers") and not d.get("judged"):
                print("NO JUDGEMENT (key)", k)
            if d["fallback"] == d["class"] and ("covers" in d or "judged" in d):
                print("JUDGEMENT LEFT (not on a key)", k)
            if "why" in d and d["class"] != "READ" and "judged" not in d:
                print("JUDGEMENT LEFT (a why, not READ)", k)
        for k, why in sorted(doc["unread"].items()):
            if not why:
                print("NO JUDGEMENT (unread)", k)
        for k, why in sorted(doc.get("untyped", {}).items()):
            if not why:
                print("NO JUDGEMENT (untyped)", k)
        sys.exit(0)
    s1, rows = census()
    for ph in ("A", "B"):
        print("STEP1", ph, len(s1[ph]), sorted(s1[ph]))
    by = defaultdict(int)
    for (place, phase, hit), r in rows.items():
        by[(phase, r["class"])] += 1
    print("ROWS", len(rows), dict(sorted(by.items())))
    print("ENTRIES", len({x for r in rows.values() for x in r["entries"]}))
    if "--rows" in sys.argv:
        for (place, phase, hit), r in sorted(rows.items(), key=lambda kv: (kv[1]["class"], kv[0][1], kv[0][0])):
            if r["class"] != "CLEAR":
                print(r["class"], phase, place, list(hit), len(r["entries"]), r["entries"][:3])
